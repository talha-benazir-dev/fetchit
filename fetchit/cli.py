"""Argument parsing + command dispatch for fetchit."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys

from . import __version__
from . import config as config_mod
from . import core
from . import history as history_mod
from . import ui as ui_mod


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fetchit",
        description="Download YouTube videos/playlists with yt-dlp. Includes a full-screen terminal interface.",
    )
    p.add_argument("url", nargs="*", help="video/playlist/channel URL(s). Omit with --batch-file/--search.")
    p.add_argument("-V", "--version", action="version", version=f"fetchit {__version__}")

    # output
    p.add_argument("-o", "--output-dir", help="download directory (default: ~/Videos)")
    p.add_argument("--output-template", default=None, help='yt-dlp -o template, e.g. "%%(title)s [%%(id)s].%%(ext)s"')
    p.add_argument("--batch-file", "-a", default=None, help="file with one URL per line")

    # quality / format
    p.add_argument("-q", "--quality", default=None,
                   help="best, worst, 144,240,360,480,720,1080,1440,2160 (p suffix ok)")
    p.add_argument("-f", "--format", default=None,
                   help="container to merge to: mp4, mkv, webm, best")
    p.add_argument("--audio-only", action="store_true", help="extract audio only")
    p.add_argument("--audio-format", default=None, help="mp3, m4a, opus, wav, flac")
    p.add_argument("--audio-quality", default=None, help="0 (best) - 10, or e.g. 192K")

    # playlist
    p.add_argument("--playlist", action="store_true", help="force playlist download (default behavior)")
    p.add_argument("--no-playlist", action="store_true", help="only the single video even if URL is a playlist")
    p.add_argument("--playlist-start", type=int, default=None)
    p.add_argument("--playlist-end", type=int, default=None)
    p.add_argument("--playlist-items", default=None, help='e.g. "1-3,7" (passed to --playlist-items)')

    # subs
    p.add_argument("--subs", action="store_true", help="download subtitles")
    p.add_argument("--subs-lang", default=None, help='langs, e.g. "en" or "en,ur,hi" (default: en)')
    p.add_argument("--auto-subs", action="store_true", help="allow auto-generated captions")
    p.add_argument("--embed-subs", action="store_true", help="embed subtitles into file")
    p.add_argument("--subs-only", action="store_true", help="only download subtitles, skip media")

    # thumb / metadata
    p.add_argument("--embed-thumbnail", action="store_true", help="embed thumbnail (on by default, see config)")
    p.add_argument("--no-embed-thumbnail", action="store_true")
    p.add_argument("--embed-metadata", action="store_true", help="embed metadata+chapters (on by default)")
    p.add_argument("--no-embed-metadata", action="store_true")

    # sponsorblock
    p.add_argument("--sponsorblock", default=None,
                   help='"mark", "remove", "all", "off", or category list e.g. "sponsor,intro,outro"')
    p.add_argument("--sponsorblock-categories", default="sponsor,intro,outro,selfpromo,preview,filler,music_offtopic",
                   help="categories for mark/remove mode")

    # network / robustness
    p.add_argument("--retries", type=int, default=None)
    p.add_argument("--concurrent", type=int, default=None, help="concurrent fragments (default 4)")
    p.add_argument("--rate-limit", default=None, help='e.g. "1M", "500K"')
    p.add_argument("--no-overwrite", action="store_true")
    p.add_argument("--force", action="store_true", help="overwrite existing media and restart partial downloads")
    p.add_argument("--proxy", default=None)
    p.add_argument("--cookies", default=None, help="path to cookies.txt")
    p.add_argument("--user-agent", default=None)

    # verbosity
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="print yt-dlp command without downloading")

    # ux / modes
    p.add_argument("--interactive", "-i", action="store_true", help="prompt for quality/format/options")
    p.add_argument("--search", default=None, help='search YouTube, e.g. --search "lofi hip hop"')
    p.add_argument("--max-results", type=int, default=5, help="results for --search (default 5)")
    p.add_argument("--print-url", action="store_true", help="with --search: only print URLs, don't download")

    # config / history
    p.add_argument("--show-config", action="store_true")
    p.add_argument("--save-as-default", action="store_true",
                   help="save current quality/format/audio/subs choices to config file")
    p.add_argument("--history", action="store_true", help="show download history")
    p.add_argument("--clear-history", action="store_true")
    p.add_argument("--history-limit", type=int, default=20)


    return p


def do_interactive(args) -> None:
    print("== fetchit interactive ==")
    q = input(f"quality [{args.quality or 'best'}]: ").strip()
    if q:
        args.quality = q
    if not args.audio_only:
        f = input(f"format mp4/mkv/webm/best [{args.format or 'mp4'}]: ").strip()
        if f:
            args.format = f
    a = input("audio-only? [y/N]: ").strip().lower()
    if a in ("y", "yes"):
        args.audio_only = True
        af = input(f"audio format [{args.audio_format or 'mp3'}]: ").strip()
        if af:
            args.audio_format = af
    s = input("subtitles? [y/N]: ").strip().lower()
    if s in ("y", "yes"):
        args.subs = True
        sl = input(f"subs lang [{args.subs_lang or 'en'}]: ").strip()
        if sl:
            args.subs_lang = sl
    if not args.url and not args.batch_file and not args.search:
        u = input("URL: ").strip()
        if u:
            args.url = [u]


def do_search(args) -> int:
    from .jobs import search_command, parse_search
    cmd = search_command(args.search, args.max_results)
    if args.dry_run:
        print("$ " + core.display_command(cmd))
        return 0
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode:
        print(proc.stderr.strip() or f"search failed (exit {proc.returncode})", file=sys.stderr)
        return 1
    results = parse_search(proc.stdout)
    if not results:
        print("no results found.", file=sys.stderr)
        return 1
    if args.print_url:
        for item in results:
            print(item["url"])
        return 0
    args.url = [item["url"] for item in results]
    args.search = None
    return -1


def _main(argv=None) -> int:
    # split off passthrough after bare --
    raw = sys.argv[1:] if argv is None else list(argv)
    passthrough: list[str] = []
    if "--" in raw:
        idx = raw.index("--")
        passthrough = raw[idx + 1:]
        raw = raw[:idx]

    parser = build_parser()
    args = parser.parse_intermixed_args(raw)
    args.ultimately_extra_opts = passthrough  # consumed by core.build_command

    cfg = config_mod.load_config()

    # fill defaults from config for display/interactive
    if args.quality is None:
        args.quality = cfg.get("quality", "best")
    if args.format is None:
        args.format = cfg.get("format", "mp4")
    if args.audio_format is None:
        args.audio_format = cfg.get("audio_format", "mp3")

    if args.show_config:
        print(config_mod.show_config(cfg))
        return 0
    if args.history:
        print(history_mod.show(args.history_limit))
        return 0
    if args.clear_history:
        history_mod.clear()
        print("history cleared.")
        return 0

    if args.interactive:
        do_interactive(args)

    if args.save_as_default:
        cfg.update({
            "quality": args.quality,
            "format": args.format,
            "audio_format": args.audio_format,
            "audio_quality": args.audio_quality or cfg.get("audio_quality", "0"),
            "subs_lang": args.subs_lang or cfg.get("subs_lang", "en"),
        })
        if args.output_dir:
            cfg["output_dir"] = args.output_dir
        core.validate_options(args, cfg)
        config_mod.save_config(cfg)
        print(f"saved defaults to {config_mod.CONFIG_FILE}")

    if args.search:
        rc = do_search(args)
        if rc != -1:
            return rc

    if not args.url and not args.batch_file and not args.search:
        # No target given: launch the interactive menu instead of dumping help.
        # `fetchit --help` / `-h` still prints help via argparse.
        if args.save_as_default:
            return 0
        if not sys.stdin.isatty():
            parser.print_help()
            return 0
        from . import tui
        rc = tui.run(cfg, dry_run=args.dry_run) if tui.available() else ui_mod.main_menu(cfg, dry_run=args.dry_run)
        if rc == 2:
            parser.print_help()
        return rc

    # warn if yt-dlp missing / ffmpeg missing
    if not shutil.which("ffmpeg"):
        print("warning: ffmpeg not found; merging mp4/mkv and audio extract may fail.", file=sys.stderr)

    try:
        cmd = core.build_command(args, cfg)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 1

    rc = core.run(cmd, dry_run=args.dry_run)
    # record history (one row per url; batch-file counted as one)
    targets = list(args.url or [])
    if args.batch_file:
        targets.append(f"batch:{args.batch_file}")
    for t in ([] if args.dry_run else targets):
        try:
            history_mod.add(t, status="dry-run" if args.dry_run else ("ok" if rc == 0 else "cancelled" if rc == 130 else f"exit-{rc}"))
            history_mod.log(f"rc={rc} target recorded")
        except OSError as exc:
            print(f"warning: history could not be saved: {exc}", file=sys.stderr)
    return rc


def main(argv=None) -> int:
    try:
        return _main(argv)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except EOFError:
        return 0
    except KeyboardInterrupt:
        print("\ncancelled.", file=sys.stderr)
        return 130
