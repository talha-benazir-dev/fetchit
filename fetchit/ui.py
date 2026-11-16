"""Proper interactive menu UI for fetchit (stdlib only, ANSI colors)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from urllib.parse import urlparse, parse_qs
from types import SimpleNamespace

from . import config as config_mod
from . import core
from . import history as history_mod

BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"


def clear() -> None:
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="", flush=True)


def banner() -> None:
    print(f"{BOLD}{CYAN}  __     _       _     _ _ {RESET}")
    print(f"{BOLD}{CYAN} / _|___| |_ ___| |__ (_) |_{RESET}")
    print(f"{BOLD}{CYAN}| |_/ _ \\ __/ __| '_ \\| | __|{RESET}")
    print(f"{BOLD}{CYAN}| ||  __/ || (__| | | | | |_{RESET}")
    print(f"{BOLD}{CYAN}|_| \\___|\\__\\___|_| |_|_|\\__|{RESET}")
    print(f"{DIM}  yt-dlp downloader  →  ~/Videos{RESET}\n")


def pause() -> None:
    input(f"\n{DIM}press Enter to continue...{RESET}")


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{BOLD}{prompt}{RESET}{DIM}{suffix}:{RESET} ").strip()
    return val if val else default


def choose(prompt: str, options: list[str], default_idx: int = 0) -> int:
    print(f"\n{BOLD}{prompt}{RESET}")
    for i, opt in enumerate(options, 1):
        marker = f" {GREEN}← default{RESET}" if (i - 1) == default_idx else ""
        print(f"  {CYAN}{i}{RESET}) {opt}{marker}")
    while True:
        raw = input(f"choice [1-{len(options)}]: ").strip()
        if not raw:
            return default_idx
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        print(f"{RED}enter a number 1-{len(options)}{RESET}")


def confirm(prompt: str, default_no: bool = True) -> bool:
    hint = "y/N" if default_no else "Y/n"
    val = input(f"{prompt} [{hint}]: ").strip().lower()
    if not val:
        return not default_no
    return val in ("y", "yes")


_DRY_RUN = False


def make_args(cfg: dict) -> SimpleNamespace:
    return SimpleNamespace(
        output_dir=cfg.get("output_dir"),
        output_template=None,
        audio_only=False,
        audio_format=cfg.get("audio_format", "mp3"),
        audio_quality=cfg.get("audio_quality", "0"),
        quality=cfg.get("quality", "best"),
        format=cfg.get("format", "mp4"),
        no_playlist=False,
        playlist_start=None,
        playlist_end=None,
        playlist_items=None,
        subs=False,
        subs_lang=cfg.get("subs_lang", "en"),
        auto_subs=False,
        embed_subs=False,
        subs_only=False,
        embed_thumbnail=False,
        no_embed_thumbnail=False,
        embed_metadata=False,
        no_embed_metadata=False,
        sponsorblock="off",
        sponsorblock_categories="sponsor,intro,outro,selfpromo,preview,filler,music_offtopic",
        retries=cfg.get("retries", 10),
        concurrent=cfg.get("concurrent_fragments", 4),
        no_overwrite=False,
        force=False,
        rate_limit=None,
        proxy=None,
        cookies=None,
        user_agent=None,
        quiet=False,
        verbose=False,
        dry_run=_DRY_RUN,
        batch_file=None,
        url=[],
        ultimately_extra_opts=[],
    )


def run_download(args: SimpleNamespace, cfg: dict) -> int:
    if not shutil.which("ffmpeg"):
        print(f"{YELLOW}warning: ffmpeg not found; merging/extract may fail.{RESET}")
    try:
        cmd = core.build_command(args, cfg)
    except (SystemExit, ValueError, OSError) as e:
        print(f"{RED}{e}{RESET}")
        return 1
    rc = core.run(cmd, dry_run=args.dry_run)
    targets = list(args.url or [])
    if args.batch_file:
        targets.append(f"batch:{args.batch_file}")
    for t in ([] if args.dry_run else targets):
        try:
            history_mod.add(t, status="dry-run" if args.dry_run else ("ok" if rc == 0 else "cancelled" if rc == 130 else f"exit-{rc}"))
        except OSError as exc:
            print(f"warning: could not save history: {exc}")
    if rc == 0:
        print(f"\n{GREEN}✔ done → {args.output_dir or cfg.get('output_dir')}{RESET}")
    else:
        print(f"\n{RED}✘ failed (exit {rc}){RESET}")
    return rc


def flow_video(cfg: dict) -> None:
    clear(); banner()
    print(f"{BOLD}── Download video ──{RESET}\n")
    url = ask("paste video URL")
    if not url:
        print(f"{RED}no URL, cancelled.{RESET}"); pause(); return
    qualities = list(config_mod.QUALITIES)
    qi = choose("quality?", qualities, default_idx=qualities.index(cfg.get("quality", "best")))
    formats = ["mp4", "mkv", "webm", "best (no remux)"]
    fi = choose("container?", formats, default_idx=["mp4", "mkv", "webm", "best"].index(cfg.get("format", "mp4")))
    args = make_args(cfg)
    args.url = [url]
    args.quality = qualities[qi]
    args.format = "best" if formats[fi].startswith("best") else formats[fi]
    if confirm("download subtitles?"):
        args.subs = True
        args.subs_lang = ask("subtitle langs (comma)", "en")
        args.embed_subs = confirm("embed subs into file?")
    if "list" in parse_qs(urlparse(url).query) and confirm("URL looks like a playlist — download only this video?", default_no=False):
        args.no_playlist = True
    args.sponsorblock = "remove" if confirm("remove sponsor segments (SponsorBlock)?") else "off"
    print()
    run_download(args, cfg)
    pause()


def flow_audio(cfg: dict) -> None:
    clear(); banner()
    print(f"{BOLD}── Audio only ──{RESET}\n")
    url = ask("paste video/playlist URL")
    if not url:
        print(f"{RED}no URL, cancelled.{RESET}"); pause(); return
    fmts = list(config_mod.AUDIO_FORMATS)
    fi = choose("audio format?", fmts, default_idx=fmts.index(cfg.get("audio_format", "mp3")))
    args = make_args(cfg)
    args.url = [url]
    args.audio_only = True
    args.audio_format = fmts[fi]
    print()
    run_download(args, cfg)
    pause()


def flow_playlist(cfg: dict) -> None:
    clear(); banner()
    print(f"{BOLD}── Playlist / channel ──{RESET}\n")
    url = ask("paste playlist/channel URL")
    if not url:
        print(f"{RED}no URL, cancelled.{RESET}"); pause(); return
    args = make_args(cfg)
    args.url = [url]
    if confirm("limit range (e.g. items 1-5)?"):
        rng = ask("items, e.g. 1-5 (blank = all)", "")
        if rng:
            args.playlist_items = rng
    qualities = list(config_mod.QUALITIES)
    qi = choose("quality?", qualities, default_idx=qualities.index(cfg.get("quality", "best")))
    args.quality = qualities[qi]
    print()
    run_download(args, cfg)
    pause()


def flow_search(cfg: dict) -> None:
    clear(); banner()
    print(f"{BOLD}── Search YouTube ──{RESET}\n")
    q = ask("search query")
    if not q:
        print(f"{RED}no query, cancelled.{RESET}"); pause(); return
    n = ask("how many results?", "5")
    try:
        max_n = max(1, min(10, int(n)))
    except ValueError:
        max_n = 5
    from .jobs import search_command, parse_search
    try:
        cmd = search_command(q, max_n)
        if _DRY_RUN:
            print("$ " + core.display_command(cmd))
            pause()
            return
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode:
            print(proc.stderr.strip() or f"search failed (exit {proc.returncode})")
            pause()
            return
        pairs = [(item["title"], item["url"]) for item in parse_search(proc.stdout)]
    except (SystemExit, OSError, ValueError) as exc:
        print(f"{RED}{exc}{RESET}")
        pause()
        return
    if not pairs:
        print(f"{RED}no results.{RESET}"); pause(); return
    print(f"{BOLD}results:{RESET}")
    for i, (title, vid) in enumerate(pairs, 1):
        print(f"  {CYAN}{i}{RESET}) {title}\n     {DIM}{vid}{RESET}")
    raw = ask(f"\nnumbers to download (e.g. 1,3 or 1-3, 0=all, blank=cancel)", "")
    if not raw:
        return
    if raw.strip() == "0":
        picked = list(range(len(pairs)))
    else:
        picked = set()
        for part in raw.split(","):
            part = part.strip()
            if "-" in part:
                try:
                    a, b = part.split("-", 1)
                    picked.update(range(int(a) - 1, int(b)))
                except ValueError:
                    pass
            elif part.isdigit():
                picked.add(int(part) - 1)
        picked = sorted(p for p in picked if 0 <= p < len(pairs))
    if not picked:
        print(f"{RED}nothing selected.{RESET}"); pause(); return
    args = make_args(cfg)
    args.url = [pairs[i][1] for i in picked]
    args.quality = cfg.get("quality", "best")
    args.format = cfg.get("format", "mp4")
    print()
    run_download(args, cfg)
    pause()


def flow_batch(cfg: dict) -> None:
    clear(); banner()
    print(f"{BOLD}── Batch file ──{RESET}\n")
    path = ask("path to file (one URL per line)")
    if not path:
        print(f"{RED}cancelled.{RESET}"); pause(); return
    args = make_args(cfg)
    args.batch_file = path
    print()
    run_download(args, cfg)
    pause()


def flow_history() -> None:
    clear(); banner()
    print(f"{BOLD}── History ──{RESET}\n")
    print(history_mod.show(20))
    if confirm("\nclear history?"):
        history_mod.clear()
        print(f"{GREEN}cleared.{RESET}")
    pause()


def flow_settings(cfg: dict) -> dict:
    clear(); banner()
    print(f"{BOLD}── Settings ──{RESET}\n")
    print(config_mod.show_config(cfg))
    if confirm("\nchange settings?"):
        cfg["output_dir"] = ask("download folder", cfg.get("output_dir", ""))
        q = ask("default quality (best/720/1080/...)", cfg.get("quality", "best"))
        cfg["quality"] = q or cfg.get("quality", "best")
        f = ask("default container (mp4/mkv/webm)", cfg.get("format", "mp4"))
        cfg["format"] = f or cfg.get("format", "mp4")
        config_mod.save_config(cfg)
        print(f"{GREEN}saved → {config_mod.CONFIG_FILE}{RESET}")
        cfg = config_mod.load_config()
    else:
        pause()
        return cfg
    pause()
    return cfg


def _main_menu(cfg: dict, dry_run: bool = False) -> int:
    global _DRY_RUN
    _DRY_RUN = dry_run
    while True:
        clear(); banner()
        print(f"{DIM}downloads go to: {BOLD}{cfg.get('output_dir')}{RESET}\n")
        print(f"  {CYAN}1{RESET}) 🎬  download video")
        print(f"  {CYAN}2{RESET}) 🎵  audio only (mp3/m4a/...)")
        print(f"  {CYAN}3{RESET}) 📃  playlist / channel")
        print(f"  {CYAN}4{RESET}) 🔍  search YouTube")
        print(f"  {CYAN}5{RESET}) 📦  batch file")
        print(f"  {CYAN}6{RESET}) 🕘  history")
        print(f"  {CYAN}7{RESET}) ⚙   settings")
        print(f"  {CYAN}0{RESET}) quit\n")
        try:
            choice = input(f"{BOLD}fetchit › {RESET}").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if choice in ("1", "v", "video"):
            flow_video(cfg)
        elif choice in ("2", "a", "audio"):
            flow_audio(cfg)
        elif choice in ("3", "p", "playlist"):
            flow_playlist(cfg)
        elif choice in ("4", "s", "search"):
            flow_search(cfg)
        elif choice in ("5", "b", "batch"):
            flow_batch(cfg)
        elif choice in ("6", "h", "history"):
            flow_history()
        elif choice in ("7", "c", "settings", "config"):
            cfg = flow_settings(cfg)
        elif choice in ("0", "q", "quit", "exit"):
            print(f"{GREEN}bye!{RESET}")
            return 0
        elif choice in ("--help", "-h", "help"):
            return 2  # let caller print argparse help
        elif choice == "":
            continue
        else:
            print(f"{RED}unknown option: {choice}{RESET}")
            pause()


def main_menu(cfg: dict, dry_run: bool = False) -> int:
    try:
        return _main_menu(cfg, dry_run)
    except EOFError:
        return 0
    except KeyboardInterrupt:
        print("\ncancelled.")
        return 130
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
