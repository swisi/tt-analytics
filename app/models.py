from datetime import datetime, timezone

from .extensions import db


class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )


class User(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")
    password_hash = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class Team(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    club_name = db.Column(db.String(120), nullable=True)
    is_own_team = db.Column(db.Boolean, nullable=False, default=False)
    active = db.Column(db.Boolean, nullable=False, default=True)


class Season(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(120), unique=True, nullable=False)
    year = db.Column(db.Integer, nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True)


class Game(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    season_id = db.Column(db.Integer, db.ForeignKey("season.id"), nullable=True)
    home_team_id = db.Column("own_team_id", db.Integer, db.ForeignKey("team.id"), nullable=True)
    away_team_id = db.Column("opponent_team_id", db.Integer, db.ForeignKey("team.id"), nullable=True)
    label = db.Column(db.String(200), nullable=False)
    game_date = db.Column(db.Date, nullable=True)
    source_type = db.Column(db.String(50), nullable=False, default="opponent_film")
    notes = db.Column(db.Text, nullable=True)

    season = db.relationship("Season", foreign_keys=[season_id], lazy="joined")
    home_team = db.relationship("Team", foreign_keys=[home_team_id], lazy="joined")
    away_team = db.relationship("Team", foreign_keys=[away_team_id], lazy="joined")


class AnalysisRun(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("game.id"), nullable=False)
    focus_team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=False)
    analysis_mode = db.Column(db.String(50), nullable=False, default="opponent_scouting")
    status = db.Column(db.String(30), nullable=False, default="draft")
    provider = db.Column(db.String(80), nullable=True)
    model_name = db.Column(db.String(120), nullable=True)
    prompt_version = db.Column(db.String(50), nullable=True)
    total_clips = db.Column(db.Integer, nullable=False, default=0)
    processed_clips = db.Column(db.Integer, nullable=False, default=0)
    failed_clips = db.Column(db.Integer, nullable=False, default=0)
    notes = db.Column(db.Text, nullable=True)

    game = db.relationship("Game", backref=db.backref("analysis_runs", lazy=True, cascade="all, delete-orphan"))
    focus_team = db.relationship("Team", foreign_keys=[focus_team_id], lazy="joined")


class Clip(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey("game.id"), nullable=False)
    clip_number = db.Column(db.Integer, nullable=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(255), nullable=False)
    storage_path = db.Column(db.String(500), nullable=False)
    content_type = db.Column(db.String(120), nullable=True)
    file_size_bytes = db.Column(db.Integer, nullable=True)
    external_play_number = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(30), nullable=False, default="uploaded")

    game = db.relationship("Game", backref=db.backref("clips", lazy=True, cascade="all, delete-orphan"))


class ClipMetadata(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clip_id = db.Column(db.Integer, db.ForeignKey("clip.id"), nullable=False)
    source_kind = db.Column(db.String(50), nullable=False, default="breakdown_excel")
    payload_json = db.Column(db.JSON, nullable=False, default=dict)

    clip = db.relationship("Clip", backref=db.backref("metadata_entries", lazy=True, cascade="all, delete-orphan"))


class ClipAnalysis(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    clip_id = db.Column(db.Integer, db.ForeignKey("clip.id"), nullable=False)
    analysis_run_id = db.Column(db.Integer, db.ForeignKey("analysis_run.id"), nullable=False)
    provider = db.Column(db.String(80), nullable=False, default="gemini")
    model_name = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(30), nullable=False, default="pending")
    schema_version = db.Column(db.String(20), nullable=False, default="v1")
    confidence = db.Column(db.Float, nullable=True)
    result_json = db.Column(db.JSON, nullable=True)
    raw_text = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)

    clip = db.relationship("Clip", backref=db.backref("analyses", lazy=True, cascade="all, delete-orphan"))
    analysis_run = db.relationship("AnalysisRun", backref=db.backref("clip_analyses", lazy=True, cascade="all, delete-orphan"))


class ReportRun(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("report.id"), nullable=False)
    analysis_run_id = db.Column(db.Integer, db.ForeignKey("analysis_run.id"), nullable=False)

    analysis_run = db.relationship("AnalysisRun", lazy="joined")


class Report(TimestampMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    report_type = db.Column(db.String(50), nullable=False, default="multi_game_opponent")
    focus_team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="draft")
    summary = db.Column(db.Text, nullable=True)

    focus_team = db.relationship("Team", foreign_keys=[focus_team_id], lazy="joined")
    runs = db.relationship("ReportRun", backref="report", lazy=True, cascade="all, delete-orphan")
