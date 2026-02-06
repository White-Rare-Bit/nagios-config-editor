"""Page rendering routes (HTML templates)."""

from flask import Blueprint, render_template, redirect, url_for
from .helpers import (
    get_service,
    get_config_path,
    get_backup_manager,
    get_config
)

bp = Blueprint('pages', __name__)


@bp.route('/')
def index():
    """Redirect to Object Explorer."""
    return redirect(url_for('pages.explorer'))


@bp.route('/bulk-rename')
def bulk_rename():
    """Bulk rename interface."""
    p = get_service().parser
    types = p.get_object_types()
    return render_template('bulk_rename.html', object_types=types)


@bp.route('/find-replace')
def find_replace():
    """Find and replace interface."""
    p = get_service().parser
    types = p.get_object_types()
    return render_template('find_replace.html', object_types=types)


@bp.route('/reorganize')
def reorganize():
    """Reorganize objects interface."""
    p = get_service().parser
    types = p.get_object_types()
    files = p.get_files()
    return render_template('reorganize.html',
                           object_types=types,
                           files=files)


@bp.route('/audit-log')
def audit_log():
    """Audit log interface."""
    return render_template('audit_log.html', config_path=get_config_path())


@bp.route('/backups')
def backups():
    """Backup management interface."""
    bm = get_backup_manager()
    backup_list = bm.list_backups()
    return render_template('backups.html', backups=backup_list)


@bp.route('/validate')
def validate():
    """Configuration validation interface."""
    return render_template('validate.html')


@bp.route('/dependencies')
def dependencies():
    """Dependency graph visualization."""
    return render_template('dependencies.html')


@bp.route('/git')
def git():
    """Git version control page."""
    return render_template('git.html')


@bp.route('/settings')
def settings():
    """Settings page for configuring paths."""
    config = get_config()
    return render_template('settings.html', config=config)


@bp.route('/inheritance')
def inheritance():
    """Inheritance viewer page."""
    p = get_service().parser
    types = p.get_object_types()
    return render_template('inheritance.html', object_types=types)


@bp.route('/smart-grouping')
def smart_grouping():
    """Smart grouping suggestions page."""
    return render_template('smart_grouping.html')


@bp.route('/explorer')
def explorer():
    """Unified Object Explorer."""
    p = get_service().parser
    return render_template('explorer.html',
                           summary=p.get_summary(),
                           files=p.get_files(),
                           config_path=get_config_path())
