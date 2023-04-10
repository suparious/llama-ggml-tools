# Convert hf to pth
import os
import json
import torch
from transformers import LlamaTokenizer, LlamaForCausalLM

tokenizer = LlamaTokenizer.from_pretrained("/home/shaun/repos/text-generation-webui/models/gpt4-x-alpaca")

base_model = LlamaForCausalLM.from_pretrained(
    "/home/shaun/repos/text-generation-webui/models/gpt4-x-alpaca",
    load_in_8bit=False,
    torch_dtype=torch.float16,
    device_map={"": "cpu"},
)

base_model_sd = base_model.state_dict()

params = {
    "dim": 5120,
    "multiple_of": 256,
    "n_heads": 40,
    "n_layers": 40,
    "norm_eps": 1e-06,
    "vocab_size": -1,
}
n_layers = params["n_layers"]
n_heads = params["n_heads"]
dim = params["dim"]
dims_per_head = dim // n_heads
base = 10000.0
inv_freq = 1.0 / \
    (base ** (torch.arange(0, dims_per_head, 2).float() / dims_per_head))

def permute(w):
    return (
        w.view(n_heads, dim // n_heads // 2, 2,
               dim).transpose(1, 2).reshape(dim, dim)
    )

def unpermute(w):
    return (
        w.view(n_heads, 2, dim // n_heads // 2,
               dim).transpose(1, 2).reshape(dim, dim)
    )

def translate_state_dict_key(k):
    k = k.replace("base_model.model.", "")
    if k == "model.embed_tokens.weight":
        return "tok_embeddings.weight"
    elif k == "model.norm.weight":
        return "norm.weight"
    elif k == "lm_head.weight":
        return "output.weight"
    elif k.startswith("model.layers."):
        layer = k.split(".")[2]
        if k.endswith(".self_attn.q_proj.weight"):
            return f"layers.{layer}.attention.wq.weight"
        elif k.endswith(".self_attn.k_proj.weight"):
            return f"layers.{layer}.attention.wk.weight"
        elif k.endswith(".self_attn.v_proj.weight"):
            return f"layers.{layer}.attention.wv.weight"
        elif k.endswith(".self_attn.o_proj.weight"):
            return f"layers.{layer}.attention.wo.weight"
        elif k.endswith(".mlp.gate_proj.weight"):
            return f"layers.{layer}.feed_forward.w1.weight"
        elif k.endswith(".mlp.down_proj.weight"):
            return f"layers.{layer}.feed_forward.w2.weight"
        elif k.endswith(".mlp.up_proj.weight"):
            return f"layers.{layer}.feed_forward.w3.weight"
        elif k.endswith(".input_layernorm.weight"):
            return f"layers.{layer}.attention_norm.weight"
        elif k.endswith(".post_attention_layernorm.weight"):
            return f"layers.{layer}.ffn_norm.weight"
        elif k.endswith("rotary_emb.inv_freq") or "lora" in k:
            return None
        else:
            print(layer, k)
            raise NotImplementedError
    else:
        print(k)
        raise NotImplementedError


new_state_dict = {}
for k, v in base_model_sd.items():
    new_k = translate_state_dict_key(k)
    if new_k is not None:
        if "wq" in new_k or "wk" in new_k:
            new_state_dict[new_k] = unpermute(v)
        else:
            new_state_dict[new_k] = v

torch.save(new_state_dict, "consolidated.00.pth")

with open("params.json", "w") as f:
    json.dump(params, f)

# Resize tensors
model = torch.load("consolidated.00.pth", map_location=torch.device('cpu'))
x = model["tok_embeddings.weight"]
y = model["output.weight"]
row_exclude = 32000
x = x[:row_exclude]
y = y[:row_exclude]
model["tok_embeddings.weight"] = x
model["output.weight"] = y
torch.save(model, "consolidated.01.pth")
# Delete consolidated.00.pth and rename consolidated.01.pth into consolidated.00.pth
