# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Agent mode: the panel chat, given tools.

Three pieces, in the order a call travels through them:

    policy.py      — may this call happen at all, and does a human have to say yes
    dispatcher.py  — which tools exist, what they take, and how to run one
    loop.py        — the conversation with the model that decides what to call

The loop speaks a provider-neutral JSON protocol rather than any vendor's
function-calling schema, because a cascade that fails over mid-task can change
provider between one step and the next; a shared format is what lets the task
survive that.
"""
