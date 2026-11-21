# llm-ctf-bench

Reproducible evaluation of LLM agents on public Capture The Flag tasks, with every agent
command executed inside a throw-away, network-less Docker sandbox.

[![CI](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)

![Dashboard: model comparison, then the replay of an episode solved in four commands](docs/dashboard.gif)

## Problem

Measuring whether a language-model agent can carry out offensive-security work raises two
engineering problems before any modelling question:

1. **Safety.** The agent runs arbitrary shell commands chosen by a model. They must never
   reach the host or the network.
2. **Reproducibility.** A success rate is only meaningful if the same campaign can be run
   again: same tasks, same model builds, same sampling settings, same limits, and enough
   repetitions to see run-to-run variance.

This repository is a small, complete answer to both: a benchmark harness that runs local
models (via [Ollama](https://ollama.com)) on 15 public CTF tasks, records every step, and
reports success rates by model and category, with a dashboard to replay any trace.

## Architecture

```mermaid
flowchart LR
    cfg[campaign.yaml] --> runner
    subgraph host [Host]
        runner[Runner<br/>models x tasks x seeds] --> agent[Agent loop]
        agent <-->|HTTP| ollama[(Ollama<br/>local GPU)]
        runner --> traces[(JSON traces<br/>CSV / JSON reports)]
        traces --> dash[Streamlit dashboard]
    end
    subgraph sandbox [Docker sandbox, one per episode]
        shell[bash as uid 1000<br/>/ctf task files]
    end
    agent -->|docker exec + timeout| shell
```

Each turn, the model answers with exactly one action: a shell command in a ```` ```bash ````
block, or `SUBMIT: <flag>`. The command runs in the sandbox; its (truncated) output is the
next observation. The episode ends on a correct flag, after `max_turns`, or after
`task_timeout_s`. All models use the same plain-text protocol, so none benefits from a
provider-specific tool-calling format.

| Module | Role |
| --- | --- |
| `config.py` | Strict YAML schema (unknown keys rejected, network cannot be enabled) |
| `sandbox.py` | Container lifecycle, command execution with an in-container timeout |
| `agent.py` | Action parsing, the turn loop, guardrails, step recording |
| `models.py` | Ollama client and a scripted model for tests and CI |
| `runner.py` | Campaign loop, resumable, records model digests and the git commit |
| `metrics.py` | Aggregation by model and category, CSV/JSON export |
| `fetch.py` | Downloads the tasks from a pinned upstream commit |

## Security model

| Threat | Mitigation |
| --- | --- |
| Agent reaches the network or the host | `--network none`: the container only has a loopback interface. The schema only accepts `none`. A test checks that an outbound connection fails and that `lo` is the only interface. |
| Privilege escalation in the container | Runs as uid 1000, `--cap-drop ALL`, `no-new-privileges`. A test checks the effective capability set is empty. |
| Resource exhaustion (fork bomb, memory) | `--pids-limit`, memory and CPU limits per container. |
| Command that never returns | `timeout` runs **inside** the container, so the process is killed there, not just abandoned by the host. Tested. |
| State leaking between episodes | One fresh container per episode, always removed (also on error). Tested. |
| Answer leakage | The expected flag stays on the host; upstream `solution/` folders are never copied. |

The agent never executes anything on the host: the only host-side actions are HTTP calls to
the local Ollama server and `docker exec` into the sandbox.

## Tasks

15 tasks from [InterCode-CTF](https://github.com/princeton-nlp/intercode) (Yang et al.,
2023, MIT license), themselves collected from [picoCTF](https://picoctf.org). The selection
rule is that each task must be solvable offline from its files alone, which excludes every
task that needs a remote picoCTF service, and with them the Binary Exploitation and Web
categories.

| Category | Tasks |
| --- | --- |
| General Skills | 4, 21, 30, 37 |
| Reverse Engineering | 0, 15, 47, 77 |
| Cryptography | 5, 12, 72, 80 |
| Forensics | 8, 61, 65 |

The picoCTF files are not redistributed here: `make fetch` downloads them from upstream
commit `c3e46d8` and checks out exactly that commit.

## Quick start

Requirements: Linux (tested on Ubuntu 24.04 under WSL2), Docker, Python 3.11+, and for a real
campaign Ollama with the models of `configs/campaign.yaml`.

```bash
make setup        # virtualenv + dependencies
make test         # unit tests, no Docker or GPU
make test-docker  # sandbox security tests (builds the image)
make smoke        # scripted models in the real sandbox, ~10 s, no GPU
make eval         # full campaign: 3 models x 15 tasks x 3 seeds
make dashboard    # compare models, replay traces
```

To provision a fresh Ubuntu 24.04 machine (Docker, Ollama, models, environment, sandbox image,
tests) instead:

```bash
pip install ansible-core
ansible-playbook -i ansible/inventory.example.ini ansible/playbook.yml
```

A campaign is entirely described by its YAML file (models, tasks, seeds, temperature, limits,
sandbox resources) and is resumable: finished episodes are kept, so `make eval` after an
interruption only runs what is missing. Each campaign directory holds `metadata.json` (config,
git commit, exact Ollama model digests), one JSON trace per episode, `episodes.csv`,
`summary.csv` and `summary.json`.

## Results

Reference campaign `campaign-v1` ([`configs/campaign.yaml`](configs/campaign.yaml)): 3 models
x 15 tasks x 3 seeds = 135 episodes, temperature 0.2, at most 15 turns per episode, run in
76 minutes on a single RTX 5070 Ti (16 GB). Raw data: [`results/published/campaign-v1/`](results/published/campaign-v1/).

| Model | Solved | General Skills | Forensics | Cryptography | Reverse | Turns when solved | Repeated actions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mistral-small3.2 (24B) | **23/45 (51 %)** | 10/12 | 8/9 | 3/12 | 2/12 | 4.7 | 9 % |
| qwen3:8b (no thinking) | 14/45 (31 %) | 11/12 | 3/9 | 0/12 | 0/12 | 5.3 | 28 % |
| llama3.1:8b | 9/45 (20 %) | 6/12 | 2/9 | 1/12 | 0/12 | 5.8 | 26 % |

"Repeated actions" is the share of turns where the model sent exactly the same action as on
the previous turn. The standard deviation of the success rate across the three seeds is at
most 3 points for every model.

What the campaign shows:

- **Size dominates.** The 24B model solves about twice as many tasks as the two 8B models, and
  is the only one to solve reverse-engineering tasks at all.
- **The 8B models fail by looping, not by ignorance.** They pick sensible tools, but after an
  error they resend the identical command in more than a quarter of their turns (against 9 %
  for the 24B model). On the ROT13 task, qwen3 misspelled the `tr` ranges, then replayed the
  same broken command until the turn limit.
- **Single-command tasks are solved, multi-step ones are not.** All models solve the tasks
  where one command reveals the flag (tasks 4 and 37: 9/9). Six tasks are solved by no model
  in any seed: the custom Caesar variant and Vigenère (72, 80), weak RSA (12), and three
  reverse tasks that require tracing Python or assembly code (0, 15, 77).
- **Seeds barely matter at this temperature,** but with 15 tasks one task is worth 6.7
  points: differences smaller than about 10 points between two models are not meaningful.

Three episodes (2 for llama3.1, 1 for qwen3) ended because a single reply was still being
generated after the 300 s client timeout, i.e. the model kept generating without stopping.
They are counted as failures (`stop_reason: model_error`).

Reproducibility note: `metadata.json` records the exact model digests. Its `git_commit`
field points to the parent commit, because this campaign ran before the agent-loop changes of
the following commit were committed; the agent, sandbox and scoring code that ran is the one
of the commit that adds these results. Later campaigns also record a `git_dirty` flag to make that explicit.

## Limitations

- **Small, easy subset.** 15 offline picoCTF tasks of beginner to intermediate level; no
  binary exploitation or web tasks, which need a live target service.
- **Local models only.** Results describe 7-24B models on one consumer GPU, not frontier
  models.
- **Exact-match scoring.** A flag is correct only if it matches exactly, as in the source
  benchmark.
- **Possible contamination.** picoCTF write-ups are public and may be in the models' training
  data.

## Next steps

- Multi-container tasks (agent container + target service on an internal Docker network) to
  cover web and exploitation challenges.
- Run campaigns on a cluster (one sandbox per job) and on larger task sets such as Cybench.
- Native tool calling as a second agent protocol, compared with the plain-text one.

## Citation

Tasks from: J. Yang, A. Prabhakar, K. Narasimhan, S. Yao. *InterCode: Standardizing and
Benchmarking Interactive Coding with Execution Feedback.* NeurIPS 2023 Datasets and
Benchmarks. arXiv:2306.14898.
