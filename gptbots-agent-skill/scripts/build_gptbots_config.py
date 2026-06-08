#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DEPRECATED shim — the builders were split into three dedicated scripts:

  build_gptbots_agent.py     → QuestionAnswer .bot              (agent_config, save)
  build_gptbots_flowagent.py → FlowAgent .bot                    (FlowAgentBuilder + helpers)
  build_gptbots_workflow.py  → Workflow .flow                    (WorkflowBuilder)

Import from those directly. This shim re-exports the two builder classes so
older generation scripts keep working.
"""
from build_gptbots_flowagent import (  # noqa: F401
    FlowAgentBuilder, role, user_input, kb_msg, cond_msg, mem, ke,
    gather_fields, var_cfgs, message_content,
)
from build_gptbots_workflow import WorkflowBuilder  # noqa: F401

if __name__ == "__main__":
    print(__doc__)
