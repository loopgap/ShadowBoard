"""
UI Tabs Package
"""

from . import diag_tab as diag_tab
from . import help_tab as help_tab
from . import memory_tab as memory_tab
from . import monitor_tab as monitor_tab
from . import queue_tab as queue_tab
from . import setup_tab as setup_tab
from . import task_tab as task_tab
from . import workflow_tab as workflow_tab

__all__ = [
	"setup_tab",
	"task_tab",
	"queue_tab",
	"workflow_tab",
	"memory_tab",
	"monitor_tab",
	"diag_tab",
	"help_tab",
]
