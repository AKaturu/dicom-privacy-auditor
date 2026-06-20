"""DICOM PS3.15 Attribute Confidentiality Profile engine.

Complete standards tables are generated locally by users and are not bundled
or redistributed by this package.
"""

from .evaluate import evaluate_pair
from .models import PolicySelection, ProfileOption
from .policy import (
    StandardsDataNotInstalledError,
    all_code_rules,
    all_rules,
    data_status,
    default_data_dir,
    get_code_rule,
    get_rule,
    resolve_code_rule,
    resolve_rule,
    table_metadata,
)

__all__ = [
    "StandardsDataNotInstalledError",
    "all_code_rules",
    "get_code_rule",
    "resolve_code_rule",
    "PolicySelection",
    "ProfileOption",
    "all_rules",
    "data_status",
    "default_data_dir",
    "evaluate_pair",
    "get_rule",
    "resolve_rule",
    "table_metadata",
]
