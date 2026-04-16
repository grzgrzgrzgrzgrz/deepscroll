# Security Policy

## Supported Versions

Security fixes are applied to:

- the latest commit on `main`
- the most recent published release, once releases exist

Older snapshots may not receive fixes.

## Reporting a Vulnerability

Please do not open public GitHub issues for suspected security problems.

Report vulnerabilities privately to:

- `grzegorzolszowka@gmail.com`

Include:

- a clear description of the issue
- impact and exploitation assumptions
- reproduction steps or a proof of concept
- any suggested mitigations

I will acknowledge receipt as quickly as possible and work toward a coordinated fix.

## Threat Model — please read before use

`deepscroll` lets a language model write Python snippets that are then
executed **in the same process** as the caller. The execution goes
through [RestrictedPython](https://restrictedpython.readthedocs.io/),
which removes dangerous names (`open`, the runtime-evaluation built-ins,
`__import__`, file-writing, raw `getattr`/`setattr` on private
attributes, etc.) from the default globals, but this is **not** a
security boundary.

### Known escapes

The RestrictedPython layer does not prevent a motivated caller
(including a prompt-injected LLM) from reaching the real CPython
`__builtins__`. For example, via an already-imported helper module that
`deepscroll` intentionally exposes (e.g. `re`):

```python
real_builtins = getattr(re.compile, "__globals__")["__builtins__"]
some_module = real_builtins["__import__"]("socket")
```

From there, any capability available to the host process is reachable:
filesystem reads and writes, arbitrary module imports, outbound
network calls, subprocess execution, reading environment variables,
etc.

This is **not** a bug in `deepscroll` specifically — it follows from the
decision to expose useful modules like `re`, `json`, `math`, and
`collections` to the navigation code. Locking this down fully would
require a separate OS-level sandbox (a subprocess with
`seccomp`/`landlock`, a container, a VM, a Wasm runtime), which is out
of scope for this project.

### What that means for you

- **Do not run `deepscroll` on untrusted inputs.** Assume any document
  or prompt you feed in can reach `__import__` and make arbitrary
  network or filesystem calls.
- **Do not run it with credentials in the environment** that you would
  not hand to the underlying LLM provider directly. API keys, SSH
  keys, cloud tokens, customer data — all of that is reachable if the
  model tries.
- **For untrusted corpora, isolate the whole process.** A container or
  VM with no secrets, no network egress, and a read-only mount of the
  data you actually want to analyze is the right posture. Nothing
  inside `deepscroll` substitutes for that.
- **Prompt injection is in scope.** A malicious document can instruct
  the LLM to write escape code. The restriction layer will not stop it.

### What `deepscroll` does try to do

- Catch obvious accidental harm from well-meaning models (e.g. a
  hallucinated `open("/etc/passwd")`).
- Fail loudly on direct use of banned names.
- Keep the set of pre-injected helper modules small and purpose-built.

That is the extent of the safety story. Treat the execution model the
same way you would treat dynamic code execution on raw LLM output —
because, for the purposes of threat modeling, that is effectively what
it is.
