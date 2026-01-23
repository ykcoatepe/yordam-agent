# Optional LaunchAgent (manual)

## Coworker runtime daemon (print-plist)

Generate a LaunchAgent for the coworker runtime daemon:

```bash
yordam-agent coworker-runtime print-plist > ~/Library/LaunchAgents/com.yordam.agent.coworker-runtime.plist
```

Use `--program /path/to/yordam-agent` if the binary is not on PATH, and add
`--enable-runtime-env` if you want the LaunchAgent to set
`YORDAM_COWORKER_RUNTIME_ENABLED=1`.

Then load/run it with `launchctl` (see steps below).

This is an opt-in, manual LaunchAgent template. It does not run on a schedule by default.

## Setup

1) Copy the template and edit the folder path and command options:

```bash
cp /Users/yordamkocatepe/Projects/yordam-agent/scripts/launchd/com.yordam.agent.reorg.plist \
  ~/Library/LaunchAgents/com.yordam.agent.reorg.plist
```

2) Edit `~/Library/LaunchAgents/com.yordam.agent.reorg.plist`:
- Replace `/path/to/folder` with your folder
- Update the command if you want `--apply` and/or `--preview`
- Update the binary path if your `yordam-agent` is elsewhere

3) Load (enable):

```bash
launchctl load ~/Library/LaunchAgents/com.yordam.agent.reorg.plist
```

4) Run manually (on demand):

```bash
launchctl kickstart -k gui/$UID/com.yordam.agent.reorg
```

5) Unload (disable):

```bash
launchctl unload ~/Library/LaunchAgents/com.yordam.agent.reorg.plist
```

## Optional scheduling

To run on a schedule, add a `StartCalendarInterval` or `StartInterval` entry in the plist.
