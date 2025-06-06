import argparse
import copy
import os
import subprocess
import uuid
from datetime import date

# Base Beaker configuration as a Python dictionary
BASE_CONFIG = {
    "version": "v2",
    "budget": "ai2/oe-adapt",
    "description": "Best of N ranking experiment",
    "tasks": [
        {
            "envVars": [
                {"name": "HF_TOKEN", "secret": "HF_TOKEN"},
                {"name": "CUDA_DEVICE_ORDER", "value": "PCI_BUS_ID"},
                {"name": "GEMINI_API_KEY", "secret": "nathan_GEMINI_API_KEY"},
                {"name": "ANTHROPIC_API_KEY", "secret": "saumyam_ANTHROPIC_API_KEY"},
                {"name": "OPENAI_API_KEY", "secret": "saumyam_OPENAI_API_KEY"},
            ],
            "command": ["/bin/sh", "-c"],
            "name": "bon_ranking",
            "image": {"beaker": "your-org/bon-ranking"},
            "constraints": {
                "cluster": ["ai2/jupiter-cirrascale-2", "ai2/saturn-cirrascale", "ai2/neptune-cirrascale"]
            },
            "context": {"priority": "normal"},
            "datasets": [{"mountPath": "/weka/oe-adapt-default", "source": {"weka": "oe-adapt-default"}}],
            "resources": {"gpuCount": 1},
            "arguments": ["python scripts/run_generative_v2.py"],
        }
    ],
}


def parse_args():
    parser = argparse.ArgumentParser()
    # Beaker-specific arguments
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        type=str,
        # nargs="+",  # allow list of models (ensemble)
        required=True,
        help="name of OpenAI model to use (TODO add more providers/models)",
    )
    parser.add_argument(
        "--dataset", type=str, required=True, help="dataset, both .jsonl (local) and huggingface format supported"
    )
    parser.add_argument("--chat_template", type=str, default=None, help="fastchat chat template (optional)")
    parser.add_argument(
        "--trust_remote_code", action="store_true", default=False, help="directly load model instead of pipeline"
    )
    parser.add_argument("--num_gpus", type=int, default=0, help="number of gpus to use, for multi-node vllm")
    parser.add_argument("--vllm_gpu_util", type=float, default=0.9, help="gpu utilization for vllm")
    # parser.add_argument("--vllm_max_seq_length", type=int, default=None, help="max sequence length for vllm")
    parser.add_argument("--do_not_save", action="store_true", help="do not save results to hub (for debugging)")
    parser.add_argument(
        "--pref_sets", action="store_true", help="run on common preference sets instead of our custom eval set"
    )
    parser.add_argument("--ties", action="store_true", default=False, help="run on ties subset specifically")
    parser.add_argument(
        "--debug", action="store_true", help="run on common preference sets instead of our custom eval set"
    )
    parser.add_argument(
        "--score_w_ratings", action="store_true", default=False, help="score with ratings instead of pairwise ranking"
    )
    parser.add_argument(
        "--num_threads", type=int, default=10, help="number of threads to use for parallel processing of examples"
    )
    parser.add_argument(
        "--disable_beaker_save", action="store_true", help="disable saving the main results in a file for AI2 Beaker"
    )
    parser.add_argument(
        "--force_local", action="store_true", default=False, help="force local run, even if model is on Together API"
    )

    parser.add_argument("--image", type=str, default="saumyam/rewardbench-2-pr-0530", help="Beaker image to use")
    parser.add_argument(
        "--cluster",
        nargs="+",
        default=["ai2/neptune-cirrascale", "ai2/saturn-cirrascale", "ai2/jupiter-cirrascale-2"],
        help="Beaker cluster to use",
    )
    parser.add_argument("--priority", type=str, default="normal", help="Priority of the job")
    parser.add_argument("--workspace", type=str, default="ai2/reward-bench-v2", help="Beaker workspace")
    parser.add_argument("--mount", type=str, default="/weka/oe-adapt-default/", help="Mount")
    parser.add_argument("--source", type=str, default="oe-adapt-default", help="Source")

    return parser.parse_args()


def create_experiment_name(args):
    model_name = args.model.split("/")[-1]
    dataset_name = args.dataset.split("/")[-1].split(".jsonl")[0]
    today = date.today().strftime("%m%d%Y")
    unique_id = str(uuid.uuid4())[:8]

    return f"rb2_{dataset_name}_{model_name}_{unique_id}_{today}".replace("/", "-")[:128]


def main():
    args = parse_args()

    # Create output directory if it doesn't exist
    os.makedirs("beaker_configs/bon_experiments", exist_ok=True)

    # Create experiment config
    config = copy.deepcopy(BASE_CONFIG)

    # Set experiment name and description
    name = create_experiment_name(args)
    config["description"] = name
    config["tasks"][0]["name"] = name

    # Configure cluster and resources
    config["tasks"][0]["image"]["beaker"] = args.image
    config["tasks"][0]["constraints"]["cluster"] = args.cluster
    config["tasks"][0]["context"]["priority"] = args.priority
    config["tasks"][0]["resources"]["gpuCount"] = args.num_gpus

    # Build base command with required parameters
    cmd_parts = ["python scripts/run_generative_v2.py", f"--dataset {args.dataset}", f"--model {args.model}"]

    # Optional parameters mapping
    optional_params = {
        "chat_template": "--chat_template",
    }

    # Add optional parameters if specified
    for param_name, cmd_arg in optional_params.items():
        value = getattr(args, param_name)
        if value is not None:
            if isinstance(value, str) and any(char.isspace() for char in value):
                cmd_parts.append(f"{cmd_arg} '{value}'")
            else:
                cmd_parts.append(f"{cmd_arg} {value}")

    # Add flags if they're True
    flag_params = [
        "do_not_save",
        "trust_remote_code",
        "debug",
        "score_w_ratings",
        "ties",
        "disable_beaker_save",
        "force_local",
    ]

    for flag in flag_params:
        if getattr(args, flag):
            cmd_parts.append(f"--{flag}")

    # Join command parts
    config["tasks"][0]["arguments"][0] = " ".join(cmd_parts)

    # Write config file
    config_path = f"beaker_configs/bon_experiments/{name}.yaml"
    with open(config_path, "w") as f:
        import yaml

        yaml.dump(config, f, default_flow_style=False)

    # Submit to Beaker
    print(f"Submitting experiment: {name}")
    beaker_cmd = f"beaker experiment create {config_path} --workspace {args.workspace}"
    subprocess.Popen(beaker_cmd, shell=True)


if __name__ == "__main__":
    main()
