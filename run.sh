#!/bin/zsh
rm -f data/*.jsonl
uv run python -m okta_soc.interface.cli --hours 24
uv run python -m okta_soc.interface.cli show-all
