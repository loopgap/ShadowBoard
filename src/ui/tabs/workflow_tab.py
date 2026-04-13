"""
Workflow Tab Logic and Event Handlers
"""

from __future__ import annotations

from typing import List, Tuple

from src.core.dependencies import get_workflow_engine

def list_workflows() -> List[str]:
    """List available workflow templates."""
    engine = get_workflow_engine()
    workflows = engine.list_workflows()
    return [f"{w.name} ({w.id})" for w in workflows]

def get_workflow_details(workflow_name: str) -> str:
    """Get details of a specific workflow."""
    if not workflow_name:
        return "Please select a workflow"
    engine = get_workflow_engine()
    workflows = engine.list_workflows()
    
    for w in workflows:
        if w.name in workflow_name or w.id in workflow_name:
            steps_info = []
            for step in w.steps:
                steps_info.append(f"  - {step.name} ({step.step_type.value})")
            
            return f"""Workflow: {w.name}
ID: {w.id}
Version: {w.version}
Description: {w.description}

Steps:
""" + "\n".join(steps_info)
    
    return "Workflow not found"

async def execute_workflow(workflow_name: str, user_input: str) -> Tuple[str, str]:
    """Execute a workflow with user input."""
    if not workflow_name:
        return "Please select a workflow", ""
    engine = get_workflow_engine()
    workflows = engine.list_workflows()
    
    workflow = None
    for w in workflows:
        if w.name in workflow_name or w.id in workflow_name:
            workflow = w
            break
    
    if not workflow:
        return "Workflow not found", ""
    
    # Execute with context
    context = {"user_input": user_input}
    
    try:
        execution = await engine.execute(workflow.id, context)
        
        if execution.state.value == "completed":
            # Get last step result
            last_result = list(execution.step_results.values())[-1] if execution.step_results else ""
            return f"Workflow completed successfully. Execution ID: {execution.id}", str(last_result)[:2000]
        else:
            return f"Workflow {execution.state.value}: {execution.error}", ""
    except Exception as e:
        return f"Workflow execution failed: {e}", ""
