"""Build and push enrich.py as a Kaggle GPU kernel (Kaggle scripts take no arguments).

    python scripts/llm_enrich/push_kaggle.py --limit 50     # pilot
    python scripts/llm_enrich/push_kaggle.py --shard 0/4    # a quarter of the backfill

Kaggle's GPU quota is 6 h/week, shared with other work, so full backfills are better
run on Colab or a desktop GPU with enrich.py directly. The kernel's output file is
llm_fields.jsonl; fetch it with `kaggle kernels output kishormorol/<slug>`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODEL = "google/gemma-4/transformers/gemma-4-12b-it/2"
DATASET = "kishormorol/researchscope-papers"

FOOTER = """

# ---- Kaggle entry point (appended by push_kaggle.py) ----
if __name__ == "__main__" and os.path.exists("/kaggle/input"):
    import glob
    import subprocess
    # vLLM needs Ampere+ (enrich.py docstring); Kaggle transformers predates Gemma 4.
    pkgs = ["-U", "transformers", "accelerate"] if "--engine" in {extra} else ["vllm"]
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *pkgs], check=True)
    configs = "/kaggle/input/**/{model_slug}/**/config.json"
    model_dir = os.path.dirname(sorted(glob.glob(configs, recursive=True))[0])
    papers = glob.glob("/kaggle/input/**/papers.parquet", recursive=True)[0]
    sys.argv = ["enrich.py", "--papers", papers,
                "--out", "/kaggle/working/llm_fields.jsonl",
                "--model", model_dir, "--model-name", "{model_slug}",
                "--dtype", "float16", *{extra}]
    main()
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--shard", default="0/1")
    ap.add_argument(
        "--engine",
        default="hf",
        choices=["hf", "vllm"],
        help="hf on Kaggle's T4s; vllm only on an Ampere+ machine shape",
    )
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--dry-run", action="store_true", help="build, don't push")
    args = ap.parse_args()

    model_slug = MODEL.split("/")[3]
    extra = ["--shard", args.shard, "--batch", str(args.batch)]
    extra += ["--limit", str(args.limit)] if args.limit else []
    extra += ["--engine", "hf"] if args.engine == "hf" else []
    tag = (
        f"pilot{args.limit}" if args.limit else f"shard{args.shard.replace('/', 'of')}"
    )
    slug = f"researchscope-llm-enrich-{tag}"

    build = HERE / "kaggle_build"
    build.mkdir(exist_ok=True)
    src = (HERE / "enrich.py").read_text()
    src = src.replace('if __name__ == "__main__":\n    main()\n', "")
    (build / "main.py").write_text(
        src + FOOTER.format(model_slug=model_slug, extra=repr(extra))
    )
    (build / "kernel-metadata.json").write_text(
        json.dumps(
            {
                "id": f"kishormorol/{slug}",
                "title": slug,
                "code_file": "main.py",
                "language": "python",
                "kernel_type": "script",
                "is_private": True,
                "enable_gpu": True,
                "enable_tpu": False,
                "enable_internet": True,
                "machine_shape": "NvidiaTeslaT4",
                "dataset_sources": [DATASET],
                "competition_sources": [],
                "kernel_sources": [],
                "model_sources": [MODEL],
            },
            indent=2,
        )
    )
    print(f"built {build / 'main.py'} -> kishormorol/{slug}")
    if not args.dry_run:
        subprocess.run(["kaggle", "kernels", "push", "-p", str(build)], check=True)


if __name__ == "__main__":
    main()
