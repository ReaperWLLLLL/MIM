# Optional remote voice setup

Use only when remote narration is requested. Native animation needs no TTS
environment. Configure the authorized SSH alias, writable remote directory, GPU
and voice in the project's voice mapping. `tts-host` and `/srv/manim-tts`
below are placeholders, not an available service.

The optional worker uses Qwen3-TTS CustomVoice on a Linux CUDA host. Inspect CUDA
compatibility and free disk/VRAM before installation. The setup helper installs
the pinned torch/torchaudio 2.8.0 cu128 pair and requirements-tts.txt; it does not
choose a compatible CUDA stack automatically.

```bash
python scripts/setup_remote_voice.py --host tts-host --remote-root /srv/manim-tts --install
python scripts/setup_remote_voice.py --host tts-host --remote-root /srv/manim-tts --download --manifest
```

These commands install packages and download weights on the named host. Use
them only after the user has authorized that setup. Running without those
flags still deploys the worker; it is not a read-only readiness probe. --host
is required. Nothing is synthesized by these preparation commands.

The helper creates a task-local environment and bootstraps pip inside it.
Installation logs and dependency records stay remote. Model content is hashed
in model-manifest.json. The worker checks supported weight hashes; a different
checkpoint requires a deliberate compatibility update. Do not equate a
model-card revision with the installed weight revision.

Synthesis uses offline model files on that host. The client verifies returned
PCM WAV bytes, samples, hashes, text and cue identities. On an observation
timeout, repeat the identical command to observe the existing detached job.
Inspect errors before changing settings; there is no automatic local/cloud
fallback. Keep cache and job records outside Git. Listen to judge pronunciation,
delivery and synchronization.

The strict v0.2 commands are in [research-video.md](research-video.md). Voice
names, credentials, cloned voice recordings and runtime records belong to the
individual project.
