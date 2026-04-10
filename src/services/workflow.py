"""
Workflow Engine Service

Provides DAG-based workflow orchestration with:
- Step dependencies
- Conditional branching
- Parallel execution
- Error handling
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
import uuid

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.models.task import Task


class StepType(Enum):
    """Types of workflow steps."""
    TASK = "task"
    CONDITION = "condition"
    PARALLEL = "parallel"
    DELAY = "delay"


class WorkflowState(Enum):
    """Workflow execution states."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WorkflowStep:
    """
    Represents a single step in a workflow.

    Attributes:
        id: Unique step identifier
        name: Human-readable name
        step_type: Type of step
        template_key: Template for task steps
        user_input: Input text (supports {prev_result} placeholder)
        depends_on: List of step IDs this depends on
        condition: Optional condition function
        on_success: Step to execute on success
        on_failure: Step to execute on failure
        delay_seconds: Delay for DELAY type steps
        parallel_steps: Sub-steps for PARALLEL type
        metadata: Additional metadata
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    step_type: StepType = StepType.TASK
    template_key: str = "custom"
    user_input: str = ""
    depends_on: List[str] = field(default_factory=list)
    condition: Optional[Callable[[Dict[str, Any]], bool]] = None
    on_success: Optional[str] = None
    on_failure: Optional[str] = None
    delay_seconds: float = 0.0
    parallel_steps: List["WorkflowStep"] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowDefinition:
    """
    Defines a complete workflow.

    Attributes:
        id: Unique workflow identifier
        name: Human-readable name
        description: Workflow description
        steps: List of workflow steps
        version: Workflow version
        metadata: Additional metadata
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = ""
    description: str = ""
    steps: List[WorkflowStep] = field(default_factory=list)
    version: str = "1.0"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_entry_steps(self) -> List[WorkflowStep]:
        """Get steps with no dependencies (entry points)."""
        return [s for s in self.steps if not s.depends_on]

    def get_step(self, step_id: str) -> Optional[WorkflowStep]:
        """Get step by ID."""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def topological_order(self) -> List[WorkflowStep]:
        """Get steps in topological order."""
        visited: Set[str] = set()
        result: List[WorkflowStep] = []

        def visit(step: WorkflowStep) -> None:
            if step.id in visited:
                return
            visited.add(step.id)

            for dep_id in step.depends_on:
                dep = self.get_step(dep_id)
                if dep:
                    visit(dep)

            result.append(step)

        for step in self.steps:
            visit(step)

        return result


@dataclass
class WorkflowExecution:
    """Tracks the execution state of a workflow."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    workflow_id: str = ""
    state: WorkflowState = WorkflowState.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    step_results: Dict[str, Any] = field(default_factory=dict)
    step_tasks: Dict[str, str] = field(default_factory=dict)  # step_id -> task_id
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "state": self.state.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "step_results": self.step_results,
            "step_tasks": self.step_tasks,
            "error": self.error,
        }


class WorkflowEngine:
    """
    Executes workflows with dependency resolution.

    Features:
    - DAG-based execution
    - Conditional branching
    - Parallel step execution
    - Error handling and recovery
    """

    def __init__(self) -> None:
        self._workflows: Dict[str, WorkflowDefinition] = {}
        self._executions: Dict[str, WorkflowExecution] = {}
        self._task_executor: Optional[Callable] = None

    def register_executor(
        self,
        executor: Callable[[Task], Any],
    ) -> None:
        """Register the task executor function."""
        self._task_executor = executor

    def register_workflow(self, workflow: WorkflowDefinition) -> None:
        """Register a workflow definition."""
        self._workflows[workflow.id] = workflow

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        """Get a registered workflow."""
        return self._workflows.get(workflow_id)

    def list_workflows(self) -> List[WorkflowDefinition]:
        """List all registered workflows."""
        return list(self._workflows.values())

    async def execute(
        self,
        workflow_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> WorkflowExecution:
        """
        Execute a workflow.

        Args:
            workflow_id: ID of workflow to execute
            context: Initial context variables

        Returns:
            WorkflowExecution with results
        """
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow not found: {workflow_id}")

        execution = WorkflowExecution(
            workflow_id=workflow_id,
            state=WorkflowState.RUNNING,
            started_at=datetime.now(),
        )
        self._executions[execution.id] = execution

        context = context or {}

        try:
            # Execute steps in topological order
            for step in workflow.topological_order():
                result = await self._execute_step(
                    step, execution, context, workflow
                )
                execution.step_results[step.id] = result

            execution.state = WorkflowState.COMPLETED
        except Exception as e:
            execution.state = WorkflowState.FAILED
            execution.error = str(e)
        finally:
            execution.completed_at = datetime.now()

        return execution

    async def _execute_step(
        self,
        step: WorkflowStep,
        execution: WorkflowExecution,
        context: Dict[str, Any],
        workflow: WorkflowDefinition,
    ) -> Any:
        """Execute a single workflow step."""
        # Check dependencies
        for dep_id in step.depends_on:
            if dep_id not in execution.step_results:
                raise RuntimeError(f"Dependency {dep_id} not yet executed")

        # Get previous result
        prev_result = ""
        if step.depends_on:
            last_dep = step.depends_on[-1]
            prev_result = execution.step_results.get(last_dep, "")

        # Substitute placeholders
        user_input = step.user_input.replace("{prev_result}", str(prev_result))

        if step.step_type == StepType.TASK:
            return await self._execute_task_step(step, user_input, execution)

        elif step.step_type == StepType.CONDITION:
            return await self._execute_condition_step(
                step, execution, context, workflow
            )

        elif step.step_type == StepType.PARALLEL:
            return await self._execute_parallel_step(
                step, execution, context, workflow
            )

        elif step.step_type == StepType.DELAY:
            await asyncio.sleep(step.delay_seconds)
            return None

        return None

    async def _execute_task_step(
        self,
        step: WorkflowStep,
        user_input: str,
        execution: WorkflowExecution,
    ) -> Any:
        """Execute a task step."""
        if not self._task_executor:
            raise RuntimeError("No task executor registered")

        task = Task(
            template_key=step.template_key,
            user_input=user_input,
            prompt=user_input,
        )

        execution.step_tasks[step.id] = task.id

        result = await self._task_executor(task)
        return result

    async def _execute_condition_step(
        self,
        step: WorkflowStep,
        execution: WorkflowExecution,
        context: Dict[str, Any],
        workflow: WorkflowDefinition,
    ) -> Any:
        """Execute a conditional step."""
        if step.condition is None:
            return None

        # Build condition context
        condition_context = {
            **context,
            **execution.step_results,
        }

        result = step.condition(condition_context)

        # Determine next step
        next_step_id = step.on_success if result else step.on_failure
        if next_step_id:
            next_step = workflow.get_step(next_step_id)
            if next_step:
                return await self._execute_step(
                    next_step, execution, context, workflow
                )

        return result

    async def _execute_parallel_step(
        self,
        step: WorkflowStep,
        execution: WorkflowExecution,
        context: Dict[str, Any],
        workflow: WorkflowDefinition,
    ) -> List[Any]:
        """Execute parallel steps."""
        tasks = [
            self._execute_step(s, execution, context.copy(), workflow)
            for s in step.parallel_steps
        ]
        return await asyncio.gather(*tasks, return_exceptions=True)

    def get_execution(self, execution_id: str) -> Optional[WorkflowExecution]:
        """Get execution by ID."""
        return self._executions.get(execution_id)

    def get_active_executions(self) -> List[WorkflowExecution]:
        """Get all active (running) executions."""
        return [
            e for e in self._executions.values()
            if e.state == WorkflowState.RUNNING
        ]


# Predefined workflow templates
def create_summary_workflow() -> WorkflowDefinition:
    """Create a summary → extract → format workflow."""
    return WorkflowDefinition(
        name="Summary Workflow",
        description="Summarize content, extract key points, then format",
        steps=[
            WorkflowStep(
                id="summarize",
                name="Summarize",
                step_type=StepType.TASK,
                template_key="summary",
                user_input="{user_input}",
            ),
            WorkflowStep(
                id="extract",
                name="Extract Key Points",
                step_type=StepType.TASK,
                template_key="extract",
                user_input="{prev_result}",
                depends_on=["summarize"],
            ),
        ],
    )


def create_translation_workflow() -> WorkflowDefinition:
    """Create a translate → review workflow."""
    return WorkflowDefinition(
        name="Translation Workflow",
        description="Translate content then review for accuracy",
        steps=[
            WorkflowStep(
                id="translate",
                name="Translate",
                step_type=StepType.TASK,
                template_key="translation",
                user_input="{user_input}",
            ),
            WorkflowStep(
                id="review",
                name="Review Translation",
                step_type=StepType.TASK,
                template_key="custom",
                user_input="Review this translation for accuracy and suggest improvements:\n\n{prev_result}",
                depends_on=["translate"],
            ),
        ],
    )
