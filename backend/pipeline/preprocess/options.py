"""Shared preprocessing command-line options."""

from types import SimpleNamespace


def add_arguments(parser):
    modes = parser.add_mutually_exclusive_group()

    modes.add_argument(
        "--binarize",
        dest="preprocess_mode",
        action="store_const",
        const="binary",
        help="Produce black-and-white images",
    )
    modes.add_argument(
        "--greyscale",
        dest="preprocess_mode",
        action="store_const",
        const="greyscale",
        help="Produce images with grey tones",
    )
    modes.add_argument(
        "--colour",
        "--color",
        "--no-binarize",
        dest="preprocess_mode",
        action="store_const",
        const="colour",
        help="Retain colour without binarizing",
    )

    parser.add_argument(
        "--no-deskew",
        action="store_true",
        default=None,
        help="Skip straightening",
    )
    parser.add_argument(
        "--no-crop",
        action="store_true",
        default=None,
        help="Skip cropping",
    )
    parser.add_argument(
        "--c",
        type=int,
        default=None,
        help="Override the binary threshold constant",
    )


def resolve_options(args, config):
    def enabled(key):
        value = config.get(key, "true").strip().lower()
        if value not in ("true", "false"):
            raise ValueError(f"{key} must be true or false")
        return value == "true"

    mode = args.preprocess_mode
    if mode is None:
        mode = (
            "binary"
            if enabled("PREPROCESS_BINARIZE")
            else "colour"
        )

    return SimpleNamespace(
        no_deskew=(
            args.no_deskew
            if args.no_deskew is not None
            else not enabled("PREPROCESS_DESKEW")
        ),
        no_crop=(
            args.no_crop
            if args.no_crop is not None
            else not enabled("PREPROCESS_CROP")
        ),
        greyscale=mode == "greyscale",
        binarize=mode == "binary",
        c=(
            args.c
            if args.c is not None
            else int(config.get("PREPROCESS_C", "20"))
        ),
    )