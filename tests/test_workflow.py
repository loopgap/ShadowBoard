"""
Tests for Workflow Engine Service
"""

from __future__ import annotations

import asyncio
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.workflow import (
    WorkflowEngine,
    WorkflowDefinition,
    WorkflowStep,
    StepType,
    create_summary_workflow,
    create_translation_workflow,
)
from src.models.task import Task


@pytest.fixture
def engine():
    """Create a WorkflowEngine instance."""
    return WorkflowEngine()


@pytest.fixture
def simple_workflow():
    """Create a simple test workflow."""
    return WorkflowDefinition(
        id="test_workflow",
        name="Test Workflow",
        description="A simple test workflow",
        steps=[
            WorkflowStep(
                id="step1",
                name="First Step",
                step_type=StepType.TASK,
                template_key="custom",
                user_input="Process: {user_input}",
            ),
            WorkflowStep(
                id="step2",
                name="Second Step",
                step_type=StepType.TASK,
                template_key="custom",
                user_input="Continue with: {prev_result}",
                depends_on=["step1"],
            ),
        ],
    )


def test_register_workflow(engine, simple_workflow):
    """Test workflow registration."""
    engine.register_workflow(simple_workflow)
    
    retrieved = engine.get_workflow(simple_workflow.id)
    assert retrieved is not None
    assert retrieved.name == "Test Workflow"


def test_list_workflows(engine, simple_workflow):
    """Test listing workflows."""
    engine.register_workflow(simple_workflow)
    
    workflows = engine.list_workflows()
    assert len(workflows) == 1
    assert workflows[0].id == simple_workflow.id


def test_topological_order(simple_workflow):
    """Test topological ordering of steps."""
    steps = simple_workflow.topological_order()
    
    # step1 should come before step2
    step_ids = [s.id for s in steps]
    assert step_ids.index("step1") < step_ids.index("step2")


def test_get_entry_steps(simple_workflow):
    """Test getting entry steps."""
    entry = simple_workflow.get_entry_steps()
    
    assert len(entry) == 1
    assert entry[0].id == "step1"


def test_execute_workflow(engine, simple_workflow):
    """Test workflow execution."""
    # Create a mock executor
    async def mock_executor(task: Task):
        return f"Executed: {task.prompt}"

    engine.register_executor(mock_executor)
    engine.register_workflow(simple_workflow)

    async def run():
        execution = await engine.execute(simple_workflow.id, {"user_input": "test data"})
        return execution

    execution = asyncio.run(run())
    
    assert execution.state.value == "completed"
    assert "step1" in execution.step_results
    assert "step2" in execution.step_results


def test_delay_step(engine):
    """Test delay step type."""
    workflow = WorkflowDefinition(
        id="delay_test",
        name="Delay Test",
        steps=[
            WorkflowStep(
                id="delay_step",
                name="Short Delay",
                step_type=StepType.DELAY,
                delay_seconds=0.1,
            ),
        ],
    )

    engine.register_workflow(workflow)

    async def run():
        import time
        start = time.time()
        execution = await engine.execute(workflow.id)
        elapsed = time.time() - start
        return execution, elapsed

    execution, elapsed = asyncio.run(run())
    
    assert execution.state.value == "completed"
    assert elapsed >= 0.1  # Should have waited at least 0.1 seconds


def test_predefined_workflows():
    """Test predefined workflow templates."""
    summary = create_summary_workflow()
    assert summary.name == "Summary Workflow"
    assert len(summary.steps) == 2
    
    translation = create_translation_workflow()
    assert translation.name == "Translation Workflow"
    assert len(translation.steps) == 2


def test_workflow_with_condition(engine):
    """Test workflow with conditional branching."""
    workflow = WorkflowDefinition(
        id="condition_test",
        name="Condition Test",
        steps=[
            WorkflowStep(
                id="check",
                name="Check Condition",
                step_type=StepType.CONDITION,
                condition=lambda ctx: ctx.get("proceed", False),
                on_success="success_step",
                on_failure="fail_step",
            ),
            WorkflowStep(
                id="success_step",
                name="Success",
                step_type=StepType.TASK,
                template_key="custom",
                user_input="Success path",
            ),
            WorkflowStep(
                id="fail_step",
                name="Failure",
                step_type=StepType.TASK,
                template_key="custom",
                user_input="Failure path",
            ),
        ],
    )

    async def mock_executor(task: Task):
        return task.prompt

    engine.register_executor(mock_executor)
    engine.register_workflow(workflow)

    async def run_true():
        return await engine.execute(workflow.id, {"proceed": True})

    async def run_false():
        return await engine.execute(workflow.id, {"proceed": False})

    # Test with condition true
    execution_true = asyncio.run(run_true())
    assert execution_true.state.value == "completed"

    # Test with condition false
    execution_false = asyncio.run(run_false())
    assert execution_false.state.value == "completed"
