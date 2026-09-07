"""Nautilus v1 unit tests.

Test modules:
- test_tools:  tool functions (read_file/write_file/edit_file/bash) + execute_tool router
- test_agent:  agent helpers (_truncate/_print_tool_call) + ReAct loop (mock LLM)
- test_llm:    create_client factory (error handling + client creation)
- test_cli:    CLI entry (__main__.main: --help, no-prompt, stdin pipe)
"""
