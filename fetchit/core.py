"""Build + run yt-dlp commands. Wraps the system yt-dlp binary."""
from __future__ import annotations

import shutil
import shlex
import sys
import re
from . import config as config_mod
import time
import codecs
from urllib.parse import urlparse
from pathlib import Path


def find_ytdlp() -> str:
    exe = shutil.which("yt-dlp")
    if not exe:
        raise SystemExit("error: yt-dlp binary not found. Install it (pacman -S yt-dlp) and retry.")
    return exe


QUALITY_MAP = {
    "best": "bestvideo+bestaudio/best",
    "worst": "worstvideo+worstaudio/worst",
    "144": "bestvideo[height<=144]+bestaudio/best[height<=144]",
    "240": "bestvideo[height<=240]+bestaudio/best[height<=240]",
    "360": "bestvideo[height<=360]+bestaudio/best[height<=360]",
    "480": "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "720": "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "1080": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "1440": "bestvideo[height<=1440]+bestaudio/best[height<=1440]",
    "2160": "bestvideo[height<=2160]+bestaudio/best[height<=2160]",
}


def _norm_quality(q: str) -> str:
    q = (q or "best").lower().strip().replace("p", "")
    return q if q in QUALITY_MAP else "best"


def build_command(args, cfg: dict) -> list[str]:
    """Build yt-dlp argv from parsed CLI args + config defaults."""
    cfg = config_mod.validate_config(cfg)
    validate_options(args, cfg)
    ytdlp = find_ytdlp()
    cmd = [ytdlp]

    # --- output ---
    out_dir = Path(args.output_dir or cfg.get("output_dir")).expanduser()
    template = args.output_template or "%(title)s [%(id)s].%(ext)s"
    cmd += ["-P", str(out_dir), "-o", template]

    # --- quality / format ---
    if args.audio_only:
        cmd += ["-x", "--audio-format", args.audio_format or cfg["audio_format"],
                "--audio-quality", args.audio_quality or cfg.get("audio_quality", "0")]
    else:
        fmt = QUALITY_MAP[_norm_quality(args.quality or cfg["quality"])]
        cmd += ["-f", fmt]
        container = (args.format or cfg["format"]).lower()
        if container in ("mp4", "mkv", "webm"):
            cmd += ["--merge-output-format", container, "--remux-video", container]
            if container == "mp4":
                cmd += ["-S", "vcodec:h264,acodec:aac"]
            elif container == "webm":
                cmd += ["-S", "vcodec:vp9,acodec:opus"]

    # --- playlist ---
    if args.no_playlist:
        cmd += ["--no-playlist"]
    else:
        if getattr(args, "playlist", False):
            cmd += ["--yes-playlist"]
        if args.playlist_start is not None:
            cmd += ["--playlist-start", str(args.playlist_start)]
        if args.playlist_end is not None:
            cmd += ["--playlist-end", str(args.playlist_end)]
        if args.playlist_items:
            cmd += ["--playlist-items", args.playlist_items]

    # --- subtitles ---
    if args.subs or args.embed_subs or args.auto_subs or args.subs_only:
        if args.auto_subs:
            cmd += ["--write-auto-subs"]
        if args.subs or args.embed_subs or args.subs_only:
            cmd += ["--write-subs"]
        cmd += ["--sub-langs", args.subs_lang or cfg.get("subs_lang", "en")]
        if args.embed_subs:
            cmd += ["--embed-subs"]
        if args.subs_only:
            cmd += ["--skip-download"]

    # --- thumbnail / metadata (on by default via config) ---
    thumb_on = args.embed_thumbnail or (cfg.get("embed_thumbnail", True) and not args.no_embed_thumbnail)
    meta_on = args.embed_metadata or (cfg.get("embed_metadata", True) and not args.no_embed_metadata)
    if thumb_on:
        cmd += ["--embed-thumbnail"]
    if meta_on:
        cmd += ["--embed-metadata", "--embed-chapters"]

    # --- sponsorblock ---
    sb = (args.sponsorblock or "off").lower()
    if sb not in ("off", "none"):
        cats = args.sponsorblock_categories
        if sb == "all":
            cmd += ["--sponsorblock-remove", "all"]
        elif sb == "remove":
            cmd += ["--sponsorblock-remove", cats]
        elif sb == "mark":
            cmd += ["--sponsorblock-mark", cats]
        else:
            # raw category list -> remove those
            cmd += ["--sponsorblock-remove", args.sponsorblock]

    # --- network / robustness ---
    cmd += ["--retries", str(args.retries if args.retries is not None else cfg.get("retries", 10))]
    cmd += ["--concurrent-fragments", str(args.concurrent or cfg.get("concurrent_fragments", 4))]
    if args.no_overwrite:
        cmd += ["--no-overwrites"]
    if args.force:
        cmd += ["--force-overwrites"]
    else:
        cmd += ["--continue"]
    if args.rate_limit:
        cmd += ["--limit-rate", args.rate_limit]
    if args.proxy:
        cmd += ["--proxy", args.proxy]
    if args.cookies:
        cmd += ["--cookies", args.cookies]
    if args.user_agent:
        cmd += ["--user-agent", args.user_agent]

    # --- verbosity / progress ---
    if args.quiet:
        cmd += ["--quiet", "--no-progress"]
    elif args.verbose:
        cmd += ["--verbose"]
    else:
        cmd += ["--progress", "--newline"]

    # --- passthrough extras after bare -- ---
    for opt in (getattr(args, "ultimately_extra_opts", None) or []):
        if opt == "--":
            continue
        cmd.append(opt)

    # --- targets ---
    if args.batch_file:
        cmd += ["-a", str(Path(args.batch_file).expanduser())]
    if args.url:
        cmd.append("--")
    for u in args.url or []:
        cmd.append(u)

    return cmd


def validate_options(args, cfg: dict) -> None:
    for attr, key in (("output_dir", "output_dir"), ("quality", "quality"),
                      ("format", "format"), ("audio_format", "audio_format"),
                      ("audio_quality", "audio_quality"), ("subs_lang", "subs_lang"),
                      ("retries", "retries"), ("concurrent", "concurrent_fragments")):
        value = getattr(args, attr, None)
        if value is None:
            value = cfg[key]
        if not config_mod.valid_value(key, value):
            raise ValueError(f"invalid {attr.replace('_', ' ')}: {value!r}")
    start, end = args.playlist_start, args.playlist_end
    if (start is not None and start < 1) or (end is not None and end < 1):
        raise ValueError("playlist start/end must be positive")
    if start is not None and end is not None and start > end:
        raise ValueError("playlist start must not exceed end")
    if args.playlist_items and not re.fullmatch(r"[0-9,:\-]+", args.playlist_items):
        raise ValueError("playlist items must be a range such as 1-5 or 1,3,7")
    for positive, negative in (("force", "no_overwrite"),
                               ("embed_thumbnail", "no_embed_thumbnail"),
                               ("embed_metadata", "no_embed_metadata"),
                               ("playlist", "no_playlist"), ("quiet", "verbose")):
        if getattr(args, positive, False) and getattr(args, negative, False):
            raise ValueError(f"--{positive.replace('_', '-')} conflicts with --{negative.replace('_', '-')}")
    if args.no_playlist and any(v is not None for v in (start, end, args.playlist_items)):
        raise ValueError("playlist range conflicts with --no-playlist")
    if args.batch_file and not Path(args.batch_file).expanduser().is_file():
        raise ValueError(f"batch file not found: {args.batch_file}")
    if args.cookies and not Path(args.cookies).expanduser().is_file():
        raise ValueError(f"cookies file not found: {args.cookies}")


def display_command(cmd: list[str]) -> str:
    """Quote arguments and conceal credentials in routine command previews."""
    result = list(cmd)
    sensitive = {"--proxy", "--cookies", "--user-agent", "--add-header", "--add-headers",
                 "--username", "--password", "--video-password", "--ap-password", "--ap-username"}
    for i, token in enumerate(cmd):
        flag, sep, value = token.partition("=")
        if flag in sensitive:
            if sep:
                result[i] = flag + "=<redacted>"
            elif i + 1 < len(result):
                result[i + 1] = "<redacted>"
    return shlex.join(result)


def anonymous_retry_command(cmd: list[str], error: str) -> list[str] | None:
    """One opt-out-friendly alternative for blocked public YouTube extraction."""
    lower = error.lower()
    if not any(marker in lower for marker in ('not a bot', 'http error 429', 'http 429', 'too many requests')):
        return None
    # Respect explicitly supplied authentication or player settings.
    if any(arg.split('=', 1)[0] in ('--cookies', '--cookies-from-browser', '--extractor-args') for arg in cmd):
        return None
    youtube_target = False
    for arg in cmd[1:]:
        try:
            host = (urlparse(arg).hostname or '').lower()
        except ValueError:
            continue
        if host == 'youtu.be' or host == 'youtube.com' or host.endswith('.youtube.com'):
            youtube_target = True
            break
    if not youtube_target:
        return None
    retry = list(cmd)
    position = retry.index('--') if '--' in retry else 1
    retry[position:position] = ['--extractor-args', 'youtube:player_client=web_embedded,tv_downgraded']
    return retry


def run(cmd: list[str], dry_run: bool = False) -> int:
    print("$ " + display_command(cmd), file=sys.stdout if dry_run else sys.stderr, flush=True)
    if dry_run:
        return 0
    from .jobs import ManagedJob
    job = None
    result = 1
    try:
        if "-P" in cmd:
            Path(cmd[cmd.index("-P") + 1]).mkdir(parents=True, exist_ok=True)
        def relay(stream):
            binary = getattr(stream, 'buffer', None)
            decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
            def write(chunk):
                if binary is not None:
                    binary.write(chunk); binary.flush()
                else:
                    stream.write(decoder.decode(chunk)); stream.flush()
            return write
        job = ManagedJob(cmd, raw_output=relay(sys.stdout), raw_error=relay(sys.stderr))
        job.start()
        while True:
            try:
                events = job.poll()
                for event in events:
                    if event.kind == 'log' and event.data.get('system'):
                        print(event.data['text'], file=sys.stderr, flush=True)
                    elif event.kind == 'complete':
                        result = event.data['returncode']
                        if result and event.data.get('error'):
                            print(event.data['error'], file=sys.stderr)
                        return result
                time.sleep(.03)
            except KeyboardInterrupt:
                job.cancel()
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        if job:
            job.close()
