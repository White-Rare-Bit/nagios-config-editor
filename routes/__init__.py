"""Flask blueprint registration for route modules."""


def register_blueprints(app):
    """Register all route blueprints with the Flask app."""
    from .pages import bp as pages_bp
    from .validation import bp as validation_bp
    from .backups import bp as backups_bp
    from .settings import bp as settings_bp
    from .git import bp as git_bp
    from .files import bp as files_bp
    from .objects import bp as objects_bp
    from .analysis import bp as analysis_bp
    from .staging import bp as staging_bp
    from .templates import bp as templates_bp
    from .debug import debug_bp
    from .metadata import bp as metadata_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(validation_bp)
    app.register_blueprint(backups_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(git_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(objects_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(staging_bp)
    app.register_blueprint(templates_bp)
    app.register_blueprint(debug_bp)
    app.register_blueprint(metadata_bp)
