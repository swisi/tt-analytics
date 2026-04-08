from collections import Counter
from datetime import datetime
from pathlib import Path
import threading
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from sqlalchemy import or_
from sqlalchemy.orm.exc import ObjectDeletedError
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import AnalysisRun, Clip, ClipAnalysis, ClipMetadata, Game, Report, ReportRun, Season, Team
from ..services.breakdown_import import parse_xlsx_rows
from ..services.gemini_analysis import analyze_clip_with_gemini

bp = Blueprint("main", __name__)


def require_login(endpoint="main.index"):
    if not session.get("user_id"):
        return redirect(url_for("auth.login", next=url_for(endpoint)))
    return None


def _collect_report_metrics(report):
    play_types = Counter()
    side_of_ball = Counter()
    formations = Counter()
    coverages = Counter()
    results = Counter()
    notes = []
    analyzed_clips = 0

    for entry in report.runs:
        for analysis in entry.analysis_run.clip_analyses:
            if analysis.status != "completed" or not analysis.result_json:
                continue

            payload = analysis.result_json
            analyzed_clips += 1

            if payload.get("play_type"):
                play_types[payload["play_type"]] += 1
            if payload.get("side_of_ball"):
                side_of_ball[payload["side_of_ball"]] += 1

            offense = payload.get("offense") or {}
            defense = payload.get("defense") or {}
            outcome = payload.get("outcome") or {}

            if offense.get("formation"):
                formations[offense["formation"]] += 1
            if defense.get("coverage"):
                coverages[defense["coverage"]] += 1
            if outcome.get("result"):
                results[outcome["result"]] += 1

            for note in payload.get("notes") or []:
                note_text = (note or "").strip()
                if note_text:
                    notes.append(note_text)

    return {
        "analyzed_clips": analyzed_clips,
        "top_play_types": play_types.most_common(5),
        "top_sides": side_of_ball.most_common(5),
        "top_formations": formations.most_common(5),
        "top_coverages": coverages.most_common(5),
        "top_results": results.most_common(5),
        "notes": notes[:12],
    }


@bp.route("/")
def index():
    login_redirect = require_login("main.index")
    if login_redirect:
        return login_redirect

    stats = {
        "teams": Team.query.count(),
        "games": Game.query.count(),
        "runs": AnalysisRun.query.count(),
        "reports": Report.query.count(),
    }
    recent_games = Game.query.order_by(Game.created_at.desc()).limit(5).all()
    recent_runs = AnalysisRun.query.order_by(AnalysisRun.created_at.desc()).limit(5).all()
    recent_reports = Report.query.order_by(Report.created_at.desc()).limit(5).all()
    return render_template("index.html", stats=stats, recent_games=recent_games, recent_runs=recent_runs, recent_reports=recent_reports)


@bp.route("/health")
def health():
    return {"status": "ok", "service": "tt-analytics"}


def _parse_game_form():
    label = (request.form.get("label") or "").strip()
    season_id = request.form.get("season_id") or None
    own_team_id = request.form.get("own_team_id") or None
    opponent_team_id = request.form.get("opponent_team_id") or None
    source_type = (request.form.get("source_type") or "opponent_film").strip()
    analysis_mode = (request.form.get("analysis_mode") or "opponent_scouting").strip()
    notes = (request.form.get("notes") or "").strip() or None
    game_date_raw = (request.form.get("game_date") or "").strip()

    if not label:
        raise ValueError("Bezeichnung des Spiels ist erforderlich.")

    game_date = None
    if game_date_raw:
        try:
            game_date = datetime.strptime(game_date_raw, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError("Ungültiges Datum.") from exc

    return {
        "label": label,
        "season_id": int(season_id) if season_id else None,
        "home_team_id": int(own_team_id) if own_team_id else None,
        "away_team_id": int(opponent_team_id) if opponent_team_id else None,
        "game_date": game_date,
        "source_type": source_type,
        "notes": notes,
    }


def _analyze_clip_for_run(clip, run):
    breakdown = ClipMetadata.query.filter_by(clip_id=clip.id, source_kind="breakdown_excel").first()
    breakdown_payload = breakdown.payload_json if breakdown else None

    analysis = ClipAnalysis.query.filter_by(clip_id=clip.id, analysis_run_id=run.id).first()
    if not analysis:
        analysis = ClipAnalysis(clip_id=clip.id, analysis_run_id=run.id, status="running")
        db.session.add(analysis)
        db.session.commit()
    else:
        analysis.status = "running"
        analysis.error_message = None
        db.session.commit()

    try:
        result = analyze_clip_with_gemini(current_app.config, clip, run, breakdown_payload)
        analysis.provider = result["provider"]
        analysis.model_name = result["model_name"]
        analysis.raw_text = result["raw_text"]
        analysis.result_json = result["result_json"]
        analysis.confidence = result.get("confidence")
        analysis.status = "completed"
        analysis.error_message = None
        db.session.commit()
        return True, None
    except Exception as exc:
        db.session.rollback()
        try:
            analysis = ClipAnalysis.query.filter_by(clip_id=clip.id, analysis_run_id=run.id).first()
            if not analysis:
                analysis = ClipAnalysis(clip_id=clip.id, analysis_run_id=run.id)
                db.session.add(analysis)
            analysis.status = "failed"
            analysis.error_message = str(exc)
            db.session.commit()
        except Exception:
            db.session.rollback()
        return False, str(exc)


def _update_run_counters(run):
    try:
        db.session.rollback()
        run = AnalysisRun.query.get(run.id)
        if not run:
            return
        analyses = ClipAnalysis.query.filter_by(analysis_run_id=run.id).all()
        run.total_clips = len(run.game.clips)
        run.processed_clips = sum(1 for item in analyses if item.status == "completed")
        run.failed_clips = sum(1 for item in analyses if item.status == "failed")
        if run.total_clips and run.processed_clips + run.failed_clips >= run.total_clips:
            run.status = "completed" if run.failed_clips == 0 else "completed_with_errors"
        elif run.processed_clips or run.failed_clips:
            run.status = "running"
        db.session.commit()
    except ObjectDeletedError:
        db.session.rollback()
    except Exception:
        db.session.rollback()
        raise


def _prepare_run_for_restart(run):
    analyses = ClipAnalysis.query.filter_by(analysis_run_id=run.id).all()
    for analysis in analyses:
        if analysis.status != "completed":
            analysis.status = "pending"
            analysis.error_message = None
    db.session.commit()
    _update_run_counters(run)


def _run_analysis_batch(app, run_id):
    with app.app_context():
        try:
            db.session.rollback()
            run = AnalysisRun.query.get(run_id)
            if not run:
                return

            clips = Clip.query.filter_by(game_id=run.game_id).order_by(Clip.clip_number.asc(), Clip.created_at.asc()).all()
            if not clips:
                run.status = "draft"
                db.session.commit()
                return

            run.status = "running"
            db.session.commit()

            for clip in clips:
                db.session.rollback()
                run = AnalysisRun.query.get(run_id)
                if not run:
                    return
                existing_analysis = ClipAnalysis.query.filter_by(clip_id=clip.id, analysis_run_id=run.id).first()
                if existing_analysis and existing_analysis.status == "completed":
                    _update_run_counters(run)
                    continue
                _analyze_clip_for_run(clip, run)
                _update_run_counters(run)
        except Exception:
            db.session.rollback()
            run = AnalysisRun.query.get(run_id)
            if run:
                run.status = "completed_with_errors"
                db.session.commit()


@bp.route("/teams", methods=["GET", "POST"])
def teams():
    login_redirect = require_login("main.teams")
    if login_redirect:
        return login_redirect

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        club_name = (request.form.get("club_name") or "").strip() or None
        is_own_team = request.form.get("is_own_team") == "on"

        if not name:
            flash("Teamname ist erforderlich.", "danger")
            return redirect(url_for("main.teams"))

        existing = Team.query.filter(db.func.lower(Team.name) == name.lower()).first()
        if existing:
            flash("Dieses Team existiert bereits.", "warning")
            return redirect(url_for("main.teams"))

        if is_own_team:
            Team.query.filter_by(is_own_team=True).update({"is_own_team": False})

        db.session.add(Team(name=name, club_name=club_name, is_own_team=is_own_team))
        db.session.commit()
        flash("Team wurde angelegt.", "success")
        return redirect(url_for("main.teams"))

    teams = Team.query.order_by(Team.is_own_team.desc(), Team.name.asc()).all()
    return render_template("teams.html", teams=teams)


@bp.route("/teams/<int:team_id>/edit", methods=["POST"])
def edit_team(team_id):
    login_redirect = require_login("main.teams")
    if login_redirect:
        return login_redirect

    team = Team.query.get_or_404(team_id)
    name = (request.form.get("name") or "").strip()
    club_name = (request.form.get("club_name") or "").strip() or None
    is_own_team = request.form.get("is_own_team") == "on"
    active = request.form.get("active") == "on"

    if not name:
        flash("Teamname ist erforderlich.", "danger")
        return redirect(url_for("main.teams"))

    existing = Team.query.filter(db.func.lower(Team.name) == name.lower(), Team.id != team.id).first()
    if existing:
        flash("Ein anderes Team mit diesem Namen existiert bereits.", "warning")
        return redirect(url_for("main.teams"))

    if is_own_team:
        Team.query.filter(Team.is_own_team.is_(True), Team.id != team.id).update({"is_own_team": False})

    team.name = name
    team.club_name = club_name
    team.is_own_team = is_own_team
    team.active = active
    db.session.commit()
    flash("Team wurde aktualisiert.", "success")
    return redirect(url_for("main.teams"))


@bp.route("/teams/<int:team_id>/delete", methods=["POST"])
def delete_team(team_id):
    login_redirect = require_login("main.teams")
    if login_redirect:
        return login_redirect

    team = Team.query.get_or_404(team_id)
    linked_games = Game.query.filter(
        or_(Game.home_team_id == team.id, Game.away_team_id == team.id)
    ).count()
    linked_runs = AnalysisRun.query.filter_by(focus_team_id=team.id).count()
    if linked_games or linked_runs:
        flash("Dieses Team kann nicht gelöscht werden, weil es noch in Spielen oder Analyse-Runs verwendet wird.", "danger")
        return redirect(url_for("main.teams"))

    db.session.delete(team)
    db.session.commit()
    flash("Team wurde gelöscht.", "success")
    return redirect(url_for("main.teams"))


@bp.route("/games", methods=["GET", "POST"])
def games():
    login_redirect = require_login("main.games")
    if login_redirect:
        return login_redirect

    teams = Team.query.order_by(Team.is_own_team.desc(), Team.name.asc()).all()
    seasons = Season.query.order_by(Season.year.desc().nullslast(), Season.label.desc()).all()

    if request.method == "POST":
        try:
            game_data = _parse_game_form()
        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("main.games"))

        game = Game(**game_data)
        db.session.add(game)
        db.session.commit()
        flash("Spiel wurde angelegt.", "success")
        return redirect(url_for("main.games"))

    games = Game.query.order_by(Game.created_at.desc()).all()
    return render_template("games.html", games=games, teams=teams, seasons=seasons)


@bp.route("/games/<int:game_id>/edit", methods=["POST"])
def edit_game(game_id):
    login_redirect = require_login("main.games")
    if login_redirect:
        return login_redirect

    game = Game.query.get_or_404(game_id)
    try:
        game_data = _parse_game_form()
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("main.games"))

    for key, value in game_data.items():
        setattr(game, key, value)
    db.session.commit()
    flash("Spiel wurde aktualisiert.", "success")
    return redirect(url_for("main.games"))


@bp.route("/games/<int:game_id>/delete", methods=["POST"])
def delete_game(game_id):
    login_redirect = require_login("main.games")
    if login_redirect:
        return login_redirect

    game = Game.query.get_or_404(game_id)
    if AnalysisRun.query.filter_by(game_id=game.id).count():
        flash("Dieses Spiel kann nicht gelöscht werden, solange Analyse-Runs dafür existieren.", "danger")
        return redirect(url_for("main.games"))
    if Clip.query.filter_by(game_id=game.id).count():
        flash("Dieses Spiel kann nicht gelöscht werden, solange Clips dafür existieren.", "danger")
        return redirect(url_for("main.games"))
    db.session.delete(game)
    db.session.commit()
    flash("Spiel wurde gelöscht.", "success")
    return redirect(url_for("main.games"))


@bp.route("/runs", methods=["GET", "POST"])
def runs():
    login_redirect = require_login("main.runs")
    if login_redirect:
        return login_redirect

    games = Game.query.order_by(Game.game_date.desc().nullslast(), Game.created_at.desc()).all()

    if request.method == "POST":
        game_id = request.form.get("game_id") or None
        focus_team_id = request.form.get("focus_team_id") or None
        analysis_mode = (request.form.get("analysis_mode") or "opponent_scouting").strip()
        notes = (request.form.get("notes") or "").strip() or None
        start_now = request.form.get("start_now") == "on"

        if not game_id or not focus_team_id:
            flash("Spiel und Fokus-Team sind erforderlich.", "danger")
            return redirect(url_for("main.runs"))

        run = AnalysisRun(
            game_id=int(game_id),
            focus_team_id=int(focus_team_id),
            analysis_mode=analysis_mode,
            status="running" if start_now else "draft",
            notes=notes,
        )
        db.session.add(run)
        db.session.commit()

        if start_now:
            app = current_app._get_current_object()
            worker = threading.Thread(target=_run_analysis_batch, args=(app, run.id), daemon=True)
            worker.start()
            flash("Analyse-Run wurde angelegt und im Hintergrund gestartet.", "success")
        else:
            flash("Analyse-Run wurde angelegt.", "success")
        return redirect(url_for("main.runs"))

    runs = AnalysisRun.query.order_by(AnalysisRun.created_at.desc()).all()
    return render_template("runs.html", runs=runs, games=games)


@bp.route("/runs/<int:run_id>/delete", methods=["POST"])
def delete_run(run_id):
    login_redirect = require_login("main.runs")
    if login_redirect:
        return login_redirect

    run = AnalysisRun.query.get_or_404(run_id)
    linked_report = ReportRun.query.filter_by(analysis_run_id=run.id).first()
    if linked_report:
        flash("Dieser Analyse-Run kann nicht gelöscht werden, weil er bereits in einem Report verwendet wird.", "danger")
        return redirect(url_for("main.runs"))

    db.session.delete(run)
    db.session.commit()
    flash("Analyse-Run wurde gelöscht.", "success")
    return redirect(url_for("main.runs"))


@bp.route("/reports", methods=["GET", "POST"])
def reports():
    login_redirect = require_login("main.reports")
    if login_redirect:
        return login_redirect

    available_runs = AnalysisRun.query.order_by(AnalysisRun.created_at.desc()).all()

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        report_type = (request.form.get("report_type") or "multi_game_opponent").strip()
        selected_run_ids = [value for value in request.form.getlist("run_ids") if value]

        if not title:
            flash("Titel ist erforderlich.", "danger")
            return redirect(url_for("main.reports"))
        if not selected_run_ids:
            flash("Mindestens ein Analyse-Run muss gewählt werden.", "danger")
            return redirect(url_for("main.reports"))

        selected_runs = AnalysisRun.query.filter(AnalysisRun.id.in_([int(v) for v in selected_run_ids])).all()
        focus_team_ids = {run.focus_team_id for run in selected_runs}
        if len(focus_team_ids) != 1:
            flash("Alle gewählten Runs müssen dasselbe Fokus-Team haben.", "danger")
            return redirect(url_for("main.reports"))

        focus_team = selected_runs[0].focus_team
        summary_lines = [
            f"Fokus-Team: {focus_team.name}",
            f"Analyse-Runs: {len(selected_runs)}",
            f"Grundlage: " + ", ".join(run.game.label for run in selected_runs),
        ]
        report = Report(
            title=title,
            report_type=report_type,
            focus_team_id=focus_team.id,
            status="draft",
            summary="\n".join(summary_lines),
        )
        db.session.add(report)
        db.session.flush()

        for run in selected_runs:
            db.session.add(ReportRun(report_id=report.id, analysis_run_id=run.id))

        db.session.commit()
        flash("Report wurde angelegt.", "success")
        return redirect(url_for("main.reports"))

    reports = Report.query.order_by(Report.created_at.desc()).all()
    return render_template("reports.html", reports=reports, available_runs=available_runs)


@bp.route("/reports/<int:report_id>")
def report_detail(report_id):
    login_redirect = require_login("main.reports")
    if login_redirect:
        return login_redirect

    report = Report.query.get_or_404(report_id)
    metrics = _collect_report_metrics(report)
    return render_template("report_detail.html", report=report, metrics=metrics)


@bp.route("/reports/<int:report_id>/delete", methods=["POST"])
def delete_report(report_id):
    login_redirect = require_login("main.reports")
    if login_redirect:
        return login_redirect

    report = Report.query.get_or_404(report_id)
    db.session.delete(report)
    db.session.commit()
    flash("Report wurde gelöscht.", "success")
    return redirect(url_for("main.reports"))


@bp.route("/games/<int:game_id>/clips", methods=["GET", "POST"])
def game_clips(game_id):
    login_redirect = require_login("main.game_clips")
    if login_redirect:
        return login_redirect

    game = Game.query.get_or_404(game_id)

    if request.method == "POST":
        uploaded_files = request.files.getlist("clips")
        uploaded_files = [file for file in uploaded_files if file and file.filename]
        if not uploaded_files:
            flash("Bitte mindestens eine Clip-Datei auswählen.", "danger")
            return redirect(url_for("main.game_clips", game_id=game.id))

        upload_root = Path(current_app.config["UPLOAD_ROOT"])
        game_dir = upload_root / f"game_{game.id}"
        game_dir.mkdir(parents=True, exist_ok=True)

        max_clip_number = db.session.query(db.func.max(Clip.clip_number)).filter_by(game_id=game.id).scalar() or 0

        created = 0
        for index, file in enumerate(uploaded_files, start=1):
            original_name = secure_filename(file.filename) or f"clip_{uuid4().hex}.mp4"
            unique_name = f"{uuid4().hex}_{original_name}"
            target = game_dir / unique_name
            file.save(target)

            clip = Clip(
                game_id=game.id,
                clip_number=max_clip_number + index,
                original_filename=original_name,
                stored_filename=unique_name,
                storage_path=str(target),
                content_type=file.content_type,
                file_size_bytes=target.stat().st_size if target.exists() else None,
                status="uploaded",
            )
            db.session.add(clip)
            created += 1

        db.session.commit()
        flash(f"{created} Clip(s) wurden hochgeladen.", "success")
        return redirect(url_for("main.game_clips", game_id=game.id))

    clips = Clip.query.filter_by(game_id=game.id).order_by(Clip.clip_number.asc(), Clip.created_at.asc()).all()
    runs = AnalysisRun.query.filter_by(game_id=game.id).order_by(AnalysisRun.created_at.desc()).all()
    return render_template("clips.html", game=game, clips=clips, runs=runs)


@bp.route("/games/<int:game_id>/breakdown", methods=["POST"])
def import_breakdown(game_id):
    login_redirect = require_login("main.game_clips")
    if login_redirect:
        return login_redirect

    game = Game.query.get_or_404(game_id)
    upload = request.files.get("breakdown_file")
    if not upload or not upload.filename:
        flash("Bitte eine Breakdown-Datei auswählen.", "danger")
        return redirect(url_for("main.game_clips", game_id=game.id))

    try:
        rows = parse_xlsx_rows(upload.read())
    except Exception:
        flash("Breakdown-Datei konnte nicht gelesen werden.", "danger")
        return redirect(url_for("main.game_clips", game_id=game.id))

    matched = 0
    unmatched = 0

    for row in rows:
        play_number = str(row.get("PLAY #", "")).strip()
        if not play_number:
            unmatched += 1
            continue

        clip = Clip.query.filter_by(game_id=game.id, clip_number=int(play_number) if play_number.isdigit() else None).first()
        if not clip:
            clip = Clip.query.filter_by(game_id=game.id, external_play_number=play_number).first()
        if not clip:
            unmatched += 1
            continue

        clip.external_play_number = play_number
        metadata = ClipMetadata.query.filter_by(clip_id=clip.id, source_kind="breakdown_excel").first()
        if not metadata:
            metadata = ClipMetadata(clip_id=clip.id, source_kind="breakdown_excel", payload_json=row)
            db.session.add(metadata)
        else:
            metadata.payload_json = row
        matched += 1

    db.session.commit()
    flash(f"Breakdown importiert: {matched} Play(s) zugeordnet, {unmatched} ohne Zuordnung.", "success" if matched else "warning")
    return redirect(url_for("main.game_clips", game_id=game.id))


@bp.route("/clips/<int:clip_id>/delete", methods=["POST"])
def delete_clip(clip_id):
    login_redirect = require_login("main.index")
    if login_redirect:
        return login_redirect

    clip = Clip.query.get_or_404(clip_id)
    clip_path = Path(clip.storage_path)
    game_id = clip.game_id
    if clip_path.exists():
        clip_path.unlink()
    db.session.delete(clip)
    db.session.commit()
    flash("Clip wurde gelöscht.", "success")
    return redirect(url_for("main.game_clips", game_id=game_id))


@bp.route("/clips/<int:clip_id>/analyze", methods=["POST"])
def analyze_clip(clip_id):
    login_redirect = require_login("main.index")
    if login_redirect:
        return login_redirect

    clip = Clip.query.get_or_404(clip_id)
    run_id = request.form.get("run_id")
    if not run_id:
        flash("Bitte einen Analyse-Run auswählen.", "danger")
        return redirect(url_for("main.game_clips", game_id=clip.game_id))

    run = AnalysisRun.query.get_or_404(int(run_id))
    if run.game_id != clip.game_id:
        flash("Der gewählte Analyse-Run gehört nicht zu diesem Spiel.", "danger")
        return redirect(url_for("main.game_clips", game_id=clip.game_id))

    ok, error = _analyze_clip_for_run(clip, run)
    _update_run_counters(run)
    if ok:
        flash("Clip wurde durch Gemini analysiert.", "success")
    else:
        flash(f"Clip-Analyse fehlgeschlagen: {error}", "danger")

    return redirect(url_for("main.game_clips", game_id=clip.game_id))


@bp.route("/runs/<int:run_id>/analyze", methods=["POST"])
def analyze_run(run_id):
    login_redirect = require_login("main.runs")
    if login_redirect:
        return login_redirect

    run = AnalysisRun.query.get_or_404(run_id)
    clips_exist = Clip.query.filter_by(game_id=run.game_id).first()
    if not clips_exist:
        flash("Dieses Spiel hat noch keine Clips.", "warning")
        return redirect(url_for("main.runs"))

    _prepare_run_for_restart(run)
    run.status = "queued"
    db.session.commit()

    app = current_app._get_current_object()
    worker = threading.Thread(target=_run_analysis_batch, args=(app, run.id), daemon=True)
    worker.start()
    flash(f"Run {run.id} wurde im Hintergrund gestartet.", "success")
    return redirect(url_for("main.runs"))
