# GuoBaoCanvas · 短剧画布 安装与运行手册

> 目标读者：**一台刚装好 Windows、什么环境都没配的新电脑**。
> 照这份文档做完，双击 `启动画布.bat` 就能在浏览器里打开画布。
> 每一步都写了「做什么 / 为什么 / 怎么确认做对了」，别跳步。

---

## 0. 这是个什么东西

一个本地运行的**短剧创作工作台**（网页界面），默认地址 `http://127.0.0.1:8766`：

- 管理「集 / 角色 / 场景 / 镜头」的文案、参考图、提示词；
- 把参数拼成 ComfyUI 工作流，由 **ComfyUI** 真正跑模型出图 / 出片；
- 画布自己**不跑模型、不占显存**，它只是驾驶舱。

所以需要两块东西：

| 组件 | 作用 | 谁提供 |
|---|---|---|
| 画布（本仓库） | 界面 + 数据 + 拼工作流 | 你正在看的这个项目 |
| ComfyUI | 真正加载模型、渲染 | 需要另外装（很重，约 20–40 GB） |

两边默认端口：画布 **8766**，ComfyUI **8188**（一般不改）。

---

## 1. 开工前的清单

| 项 | 要求 | 说明 |
|---|---|---|
| 系统 | Windows 10 / 11 64 位 | 启动脚本是 `.bat`，Linux / macOS 没有现成脚本 |
| Python | **3.10 或更新**（实测） | 只给画布用，不需要 CUDA / torch |
| ComfyUI | 建议 **0.42.1 或更新**（实测） | 太老的版本会缺 H3 官方节点（`MiniMaxH3*`），升级 ComfyUI 即可 |
| 自定义节点 | 5 个包（见第 5 步） | 其余节点全是 ComfyUI 自带 |
| 模型 | **必需 8 个，可选 4 项** | 见第 6 步；可选那组只在用「多角度 / 去人」时才要 |
| 显卡 | 建议 **24 GB 显存**（实测） | 显存小会 OOM，16 GB 很勉强 `[未在 16GB 实测]` |
| git（可选） | 装节点包用 | 不装也能用 ZIP 下载，见第 5 步 |

---

## 2. 第 1 步：把代码放到一个目录

两种方式任选：

```bat
:: 有 git（在当前目录下建一个 GuoBaoCanvas 文件夹）
git clone <本仓库地址> GuoBaoCanvas
```

或者直接在 GitHub 页面点 **Code → Download ZIP**，解压到比如 D 盘根目录下的 `GuoBaoCanvas` 文件夹。

解压后目录里应该能看到：

```
GuoBaoCanvas\
├── 启动画布.bat        ← 双击这个
├── 关闭画布.bat
├── 安装依赖.bat        ← 一键装 Python 依赖（新电脑先跑这个）
├── requirements.txt    ← Python 依赖清单
├── canvas\             ← 画布后端 + 前端
├── core\  steps\  engines\  styles\
├── tools\              ← 启动器 / 关服 / 目录选择 / 依赖安装
└── projects\           ← 你的集（首次运行后才有内容）
```

**路径建议纯英文、别太长**（例如 D 盘根目录下的 `GuoBaoCanvas`）。
中文路径 Python 本身能读（放在中文名的文件夹里也能跑），但 `pip`、个别节点脚本在中文路径上偶发怪问题，能避就避。

---

## 3. 第 2 步：装 Python（只给画布用）

1. 去 <https://www.python.org/downloads/> 下 **3.10 以上**的安装包。
2. 安装第一屏**务必勾上 `Add python.exe to PATH`**（漏了就得手动配路径）。
3. 验证——新开一个 cmd：

```bat
python --version
:: 能打印 Python 3.1x.x 才算成功
```

> 画布**不需要** CUDA、torch、GPU。显卡那些是 ComfyUI 自己的环境，别混在一起。

---

## 4. 第 3 步：装 Python 依赖

**最省事：双击 `安装依赖.bat`。**

它会自己按顺序找解释器（`..\python\python.exe` → PATH 上的 `python` → `py` 启动器）；
**一个都没找到**就自动下载官方 Python 3.12 安装包并静默安装（按当前用户装，不要管理员权限，
自动勾 PATH，自带 pip）；然后自动 `pip install -r requirements.txt`；
默认源失败会自动换清华 / 阿里镜像重试。装完窗口会停住，告诉你成功还是还缺什么。

手动方式（不想跑 bat 的话）——在项目目录下开 cmd：

```bat
cd /d <项目目录>
python -m pip install -r requirements.txt
```

国内下载慢就换源：

```bat
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

`requirements.txt` 里就这几样（版本是开发机实测，写的是下限）：

| 包 | 用在哪 |
|---|---|
| fastapi / uvicorn / pydantic / python-multipart | 画布 Web 服务 |
| numpy / opencv-python / Pillow | 拼图、缩放、封面 |
| websockets | 连 ComfyUI 收进度 |
| imageio-ffmpeg | 抽视频末帧 / 封面 |

验证：

```bat
python -c "import fastapi, uvicorn, cv2, PIL, numpy, websockets, imageio_ffmpeg; print('deps ok')"
```

打印 `deps ok` 就算过。

> 如果双击启动时窗口提示 **「缺 Python 依赖：fastapi, ...」**，就是这一步没做，或者你机器上有好几个 Python、装到了另一个上面。提示里会给出**该用哪个解释器**执行 pip，照抄即可。

---

## 5. 第 4 步：装 ComfyUI

- 建议 **0.42.1 或更新**（实测）。如果你体检时提示缺 `MiniMaxH3*` 节点，
  那不是节点包没装，是 ComfyUI 版本太老——升级 ComfyUI 即可。
- 随便用哪种发行版：ComfyUI 官方桌面版 / 官方便携包 / 秋葉整合包都行。
  官方下载页：<https://www.comfy.org/download>
- 装完先确认 ComfyUI 自己能打开：浏览器访问 `http://127.0.0.1:8188` 有界面。
- **画布只认端口 8188**；如果你改过 ComfyUI 端口，在画布设置页的「服务地址」里填新的。

---

## 6. 第 5 步：装 5 个自定义节点包

只有 5 个包，其余用到的节点全是 ComfyUI 自带（`nodes` / `comfy_extras`）。

| 包 | 装的节点 | 仓库 |
|---|---|---|
| ComfyUI-Spectrum-MiniMax-H3 | `SpectrumApplyMiniMaxH3` | <https://github.com/xmarre/ComfyUI-Spectrum-MiniMax-H3> |
| ComfyUI-H3-Latent-Relay | `H3RelaySeedFromVideo` / `H3RelayCopyBridge` / `H3RelayLatentSave` / `H3RelayTrimAV` | <https://github.com/ZenHG/ComfyUI-H3-Latent-Relay> |
| comfyui-kjnodes | `PathchSageAttentionKJ`（加速，缺了会自动退回 SDPA，只是慢） | <https://github.com/kijai/ComfyUI-KJNodes> |
| ComfyUI-RMBG | `BiRefNetRMBG`（场景「去人」用） | <https://github.com/1038lab/ComfyUI-RMBG> |
| comfyui-frame-interpolation | `RIFE VFI`（补帧用） | <https://github.com/Fannovel16/ComfyUI-Frame-Interpolation> |

**git 方式**——在 `ComfyUI\custom_nodes\` 下开 cmd，逐条执行：

```bat
cd /d <你的ComfyUI目录>\custom_nodes

git clone https://github.com/xmarre/ComfyUI-Spectrum-MiniMax-H3
git clone https://github.com/ZenHG/ComfyUI-H3-Latent-Relay
git clone https://github.com/kijai/ComfyUI-KJNodes
git clone https://github.com/1038lab/ComfyUI-RMBG
git clone https://github.com/Fannovel16/ComfyUI-Frame-Interpolation
```

**没有 git？** 打开上面每个仓库页面 → `Code` → `Download ZIP` → 解压到 `custom_nodes\`。
解压后**别套两层目录**：正确是 `custom_nodes\ComfyUI-RMBG\__init__.py`，不是 `custom_nodes\ComfyUI-RMBG\ComfyUI-RMBG\__init__.py`。

**装完必须重启 ComfyUI**，否则节点不会加载。

> 已经装了 ComfyUI-Manager 的话，也可以直接在工作流里点「Install Missing Custom Nodes」，效果一样。
>
> **文件夹在、但体检说节点缺**：说明 ComfyUI 启动时没加载成功（多半是这个包的 Python 依赖没装）。
> 去看 ComfyUI 启动日志里的 import 报错，在那个包的目录里 `pip install -r requirements.txt`；不是没装，别重复 clone。

### 5.1 还要装：SageAttention（出片快约 55%）

出片默认开 SageAttention 加速，需要 **ComfyUI 的 Python** 里有 `sageattention` 包。
注意它**不是** custom_nodes，`git clone` 装不上——它是 pip 包，要按 ComfyUI 那套 torch / CUDA 版本装。

- **最省事**：画布里「设置 → 体检」，这一项红了就点旁边的「安装 / 重装」——它会用 ComfyUI 自己的 pip 装
  （装不上会自动 `--force-reinstall`；如果是缺 `triton`，会自动改装 `triton-windows`），装完自动复查。
- **手动**（体检里会显示 ComfyUI 用的那个解释器路径）：

```bat
"<ComfyUI 的 python.exe>" -m pip install sageattention
:: Windows 上 sageattention 还依赖 triton，要用 triton-windows（不是 triton）
"<ComfyUI 的 python.exe>" -m pip install triton-windows
```

版本对不上（编译报错）时先别硬装，画布会自动摘掉加速节点，照样能出片，只是慢一倍；
也可以在右侧面板把「SageAttention 加速」设成「关」。

**RMBG 的模型**：第一次用「去人」时它会自动下载 `BiRefNet-portrait`（约 844 MB）到
`ComfyUI\models\RMBG\BiRefNet\`。国内网络下不动就手动下：
<https://huggingface.co/1038lab/BiRefNet/resolve/main/BiRefNet-portrait.safetensors>
（镜像：<https://hf-mirror.com/1038lab/BiRefNet/resolve/main/BiRefNet-portrait.safetensors>）
连同同仓库的 `birefnet.py`、`BiRefNet_config.py`、`config.json` 一起放进那个目录。

---

## 7. 第 6 步：下载模型（必需 8 个，可选 4 项）

**目录规则**：全部放进 `ComfyUI\models\<子目录>\`，子目录名必须一模一样（加载器只认这几个名字）。

**下载方法**：点链接直接下；国内连不上就把域名 `huggingface.co` 换成 `hf-mirror.com`。
文件很大（单个最大 19.5 GB），建议用 IDM / aria2 / 迅雷多线程。

### 7.1 出片链路（MiniMax H3，参考图生视频）——必需 5 个

| 文件 | 大小 | 放到 | 下载 |
|---|---|---|---|
| `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | 19.53 GB | `models\diffusion_models\` | [HF](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors) · [镜像](https://hf-mirror.com/Comfy-Org/MiniMax-H3/resolve/main/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors) |
| `minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors` | 1.82 GB | `models\loras\` | [HF](https://huggingface.co/lightx2v/Minimax-h3-Turbo/resolve/main/minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors) · [镜像](https://hf-mirror.com/lightx2v/Minimax-h3-Turbo/resolve/main/minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors) |
| `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | 14.61 GB | `models\text_encoders\` | [HF](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors) · [镜像](https://hf-mirror.com/Comfy-Org/MiniMax-H3/resolve/main/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors) |
| `minimax_h3_video_vae_int8_convrot.safetensors` | 2.62 GB | `models\vae\` | [HF](https://huggingface.co/Kijai/MiniMax-H3-experimental/resolve/main/minimax_h3_video_vae_int8_convrot.safetensors) · [镜像](https://hf-mirror.com/Kijai/MiniMax-H3-experimental/resolve/main/minimax_h3_video_vae_int8_convrot.safetensors) |
| `minimax_h3_audio_vae_fp32.safetensors` | 0.56 GB | `models\vae\` | [HF](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_audio_vae_fp32.safetensors) · [镜像](https://hf-mirror.com/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_audio_vae_fp32.safetensors) |

### 7.2 生图链路（Krea2，首帧 / 角色设定图 / 场景空镜）——必需 3 个

| 文件 | 大小 | 放到 | 下载 |
|---|---|---|---|
| `krea2_turbo_fp8_scaled.safetensors` | 12.24 GB | `models\diffusion_models\` | [HF](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/diffusion_models/krea2_turbo_fp8_scaled.safetensors) · [镜像](https://hf-mirror.com/Comfy-Org/Krea-2/resolve/main/diffusion_models/krea2_turbo_fp8_scaled.safetensors) |
| `qwen3vl_4b_fp8_scaled.safetensors` | 4.88 GB | `models\text_encoders\` | [HF](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/text_encoders/qwen3vl_4b_fp8_scaled.safetensors) · [镜像](https://hf-mirror.com/Comfy-Org/Krea-2/resolve/main/text_encoders/qwen3vl_4b_fp8_scaled.safetensors) |
| `qwen_image_vae.safetensors` | 0.24 GB | `models\vae\` | [HF](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/vae/qwen_image_vae.safetensors) · [镜像](https://hf-mirror.com/Comfy-Org/Krea-2/resolve/main/vae/qwen_image_vae.safetensors) |

### 7.3 可选：改图链路（Qwen-Image-Edit 2511，多角度三视图 / 场景去人）——4 个，约 28.9 GB

**这一组不是必需的，主流程（角色卡、场景空镜、首帧、出片）一行都用不到。** 只在你想用
「生成多角度」「生成组（表情/服装/道具）」「把场景参考里的人去掉」这三个按钮时才需要。

不装也能正常用画布：体检不会因为缺它们而拦你进画布，相关按钮会直接不显示。
等哪天要用那段功能，再回来补下载即可。

| 文件 | 大小 | 放到 | 下载 |
|---|---|---|---|
| `qwen_image_edit_2511_fp8mixed.safetensors` | 19.12 GB | `models\diffusion_models\` | [HF](https://huggingface.co/Comfy-Org/Qwen-Image-Edit/resolve/main/split_files/diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors) · [镜像](https://hf-mirror.com/Comfy-Org/Qwen-Image-Edit/resolve/main/split_files/diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors) |
| `qwen_2.5_vl_7b_fp8_scaled.safetensors` | 8.74 GB | `models\text_encoders\` | [HF](https://huggingface.co/Comfy-Org/HunyuanVideo_1.5_repackaged/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors) · [镜像](https://hf-mirror.com/Comfy-Org/HunyuanVideo_1.5_repackaged/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors) |
| `Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors` | 0.79 GB | `models\loras\` | [HF](https://huggingface.co/lightx2v/Qwen-Image-Edit-2511-Lightning/resolve/main/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors) · [镜像](https://hf-mirror.com/lightx2v/Qwen-Image-Edit-2511-Lightning/resolve/main/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors) |
| `qwen-image-edit-2511-multiple-angles-lora.safetensors` | 0.28 GB | `models\loras\` | [HF](https://huggingface.co/fal/Qwen-Image-Edit-2511-Multiple-Angles-LoRA/resolve/main/qwen-image-edit-2511-multiple-angles-lora.safetensors) · [镜像](https://hf-mirror.com/fal/Qwen-Image-Edit-2511-Multiple-Angles-LoRA/resolve/main/qwen-image-edit-2511-multiple-angles-lora.safetensors) |

> `qwen_image_vae.safetensors` 在 7.2 已经下过一次，7.3 的 VAE 就是它，不用重复下载。

### 7.4 可选：图生视频路线（fl2va）

画布主路线是 **ref2va（参考图生成）**，上面 8 个必需的够了（可选那 4 项是「多角度 / 去人」用的）。
如果你还要走「图生视频」（首帧图驱动），再补这 2 个：

| 文件 | 大小 | 放到 | 下载 |
|---|---|---|---|
| `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | 19.53 GB | `models\diffusion_models\` | [HF](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors) · [镜像](https://hf-mirror.com/Comfy-Org/MiniMax-H3/resolve/main/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors) |
| `minimax_h3_fl2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors` | 1.82 GB | `models\loras\` | [HF](https://huggingface.co/lightx2v/Minimax-h3-Turbo/resolve/main/minimax_h3_fl2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors) · [镜像](https://hf-mirror.com/lightx2v/Minimax-h3-Turbo/resolve/main/minimax_h3_fl2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors) |

### 7.5 模型想放别的盘（比如 D 盘只剩空间）

ComfyUI 支持 `extra_model_paths.yaml`：把模型放任意位置，再让 ComfyUI 挂进来。

在 `ComfyUI\extra_model_paths.yaml` 里写（注意 `base_path` 是你自己的路径）：

```yaml
comfyui:
    base_path: <你的模型存放根目录>
    diffusion_models: |
         <你的模型存放根目录>/diffusion_models
    text_encoders: |
         <你的模型存放根目录>/text_encoders
    loras: |
         <你的模型存放根目录>/loras
    vae: |
         <你的模型存放根目录>/vae
```

> 这份文件不需要手写完整版：ComfyUI 装的目录里通常有个 `extra_model_paths.yaml.example`，复制改名再改路径即可。改完重启 ComfyUI。

---

## 8. 第 7 步：启动

顺序很重要：**先 ComfyUI，后画布**。

1. 启动 ComfyUI，确认 `http://127.0.0.1:8188` 能打开。
2. 双击 **`启动画布.bat`**。
   窗口会打印每一步：
   ```
   Canvas launcher - debug mode
   work dir : <项目目录>
   launcher : tools\launch_canvas.py
   [..] 启动画布 http://127.0.0.1:8766/ …
   [..] 已用 cmd start 打开浏览器
   [..] 已启动（PID 12345），端口 8766 已就绪
   ```
3. 浏览器自动打开画布；没自动开就手动访问 `http://127.0.0.1:8766/`。

**关闭**：双击 `关闭画布.bat`（只杀 8766 上的 python，不碰 ComfyUI）。

**常用参数**：

```bat
:: 换端口（8766 被占了）
启动画布.bat --port 8770

:: 或者设环境变量
set CANVAS_PORT=8770
启动画布.bat
```

**关掉那个黑窗口会不会停服务？** 不会。服务是 detached 起的，关窗口不影响。
调试阶段建议留着窗口看日志；稳定后可以自己把 bat 里的 `python.exe` 换成 `pythonw.exe`，窗口就不再出现。

**日志位置**：

```
out\canvas_launch.log   ← 启动器每一步
out\canvas.log          ← 画布后端日志（报错都在这）
```

---

## 9. 第 8 步：画布设置页（右上角「设置」）

首次打开先做一次配置：

1. **ComfyUI 文件夹**：点「浏览…」选你 ComfyUI 的根目录（有 `main.py` / `models\` / `input\` 那一层）。
   选错层级不用慌——选成外壳目录、选进 `models\` 里，它都会自动纠正并告诉你纠到了哪。
2. **点「体检」**：逐项检查
   - 目录、服务（8188 在不在）、子目录（models / input / output）
   - **权重**：逐个查，缺的会直接列出 **HF 下载链接**、**hf-mirror 镜像**、**该放哪个目录**
   - **节点**：5 个包逐个查，缺的会给出 **`git clone` 地址**
   - 出片用的 H3 权重（ref2va / fl2va / turbo LoRA）单独列，缺了同样给链接
3. **「模拟未配置」**（勾选框）：忽略已保存的设置和环境变量，模拟一台全新机器——用来验证你手填的路径是否真的生效。
4. **高级 → 模型文件名**：你下载的文件名和默认不一样（比如换了别的量化版），在这里改名字即可，**不用改代码**。

体检全绿 = 可以出片。

### 画风怎么选（全片 / 单个素材）

- **顶栏「画风」下拉**：全片默认画风，出片和首帧都用它。新集默认 `CG 人物 + 实拍背景`（cgphoto）。
- **左栏「新建角色 / 新建场景 / 新建道具」**：弹窗里一次填 名字 + 提示词 + 画风；点「生成」直接建卡并把这张图设成主参考，点「跳过」只建空卡。默认 角色 / 道具 = 写实 CG、场景 = 写实照片；换过的选择会记在这一集里。
- **单个镜头**还能在右侧面板单独覆盖全片画风。
- 想「真人」就选 `写实照片`，想动画就选 `动画 · 赛璐璐` —— 画风词会放在提示词最前面，Krea2 才会按这个介质出图。

---

## 10. 常见问题

**Q1：双击只闪一下，或者窗口里一大串 traceback 说 `No module named 'fastapi'`**
→ 依赖没装，或装到了另一个 Python 上。**最省事：双击 `安装依赖.bat`**，它自己找解释器、自己装。
新版启动器也会直接在窗口里说：`缺 Python 依赖：fastapi, ...`，并提示去双击 `安装依赖.bat`，
同时给出该用哪个解释器执行 pip（手动补时照抄）。

**Q2：体检说缺节点，但看着都装了**
- 装完节点**必须重启 ComfyUI**。
- 报「ComfyUI 官方」的那几个（`MiniMaxH3ReferenceToVideo` 等）不是节点包，是 **ComfyUI 版本太老**，升级 ComfyUI 即可。
- 装 ZIP 的注意别套两层目录。

**Q3：体检说缺权重**
→ 照体检里给的链接下，放进它写的那一行目录（`ComfyUI\models\<子目录>\`）。下完再点一次体检。

**Q4：浏览器打不开 / 提示无法连接**
- 看 `out\canvas.log` 最后几行。
- 或者端口被别的程序占了：`netstat -ano | findstr :8766`，改用 `--port 8770`。

**Q5：模型放 D 盘，体检说找不到**
→ 第 7.5 节，用 `extra_model_paths.yaml` 挂进来；或者把模型挪回 `ComfyUI\models\` 对应子目录。

**Q6：改了 `canvas\server.py` 不生效**
→ 画布要**关掉再启动**：`关闭画布.bat` → `启动画布.bat`。
启动器发现端口已经开着时只会开浏览器、不会重启服务，所以光双击不会加载新代码。

**Q7：出片报 OOM / 特别慢**
- 显存不够：H3 主模型 19.5 GB + 文本编码器 14.6 GB，建议 24 GB 显存。
- 确认 turbo LoRA 挂上了（8 步档），并且步数没被设得过高。
- 关掉别的占显存的程序。

**Q8：ComfyUI 里报缺 `PathchSageAttentionKJ` 但不影响出片**
→ 那是 kjnodes 的 SageAttention 加速节点，缺了会自动退回 SDPA，只是慢一点。想快就装第 5 步里的 `ComfyUI-KJNodes`。

---

## 11. 显存不够（OOM）怎么办

**症状**：点「出视频」后失败，报 `CUDA out of memory` / `torch.cuda.OutOfMemoryError`，
或者 ComfyUI 控制台红字刷一片 `Allocation on device` 之类。画布这边会直接弹出「显存不够」并附下面这套建议。

**为什么会 OOM**：H3 出片要同时装两块大权重——主模型约 **19.5 GB**、文本编码器约 **14.6 GB**。
8 GB 显卡物理上塞不下，ComfyUI 只能把权重在「显存 ↔ 内存 ↔ 磁盘」之间来回换；换不过来就 OOM。
**这不是画布的 bug，也不是提示词的问题。**

按这个顺序试（越靠前越省事）：

1. **给 ComfyUI 加 `--lowvram`**（最有效）。
   整合包/便携包一般改 `run_nvidia_gpu.bat` 里那行，或在命令行里：
   ```bat
   "<ComfyUI 的 python.exe>" -s main.py --lowvram --auto-launch
   ```
   更极端的显存（≤6 GB）可以试 `--novram`，速度会更慢。
2. **把这一镜缩短**（比如 3 秒）。帧数要满足 `17k+5`，越短越省。
3. **关掉其它吃显存的程序**（浏览器视频标签、别的 AI 工具）。
4. **切到 8 GB 低配档**：右侧「出片模型档位」选「低显存（W4A8 + 4B 编码器）」，配置见下面 11.0。
5. **物理升级到 16–24 GB 显卡**——这是最省事的终点，H3 这类模型对显存就是这么吃。

**预期**：8 GB 显存不是不能跑，是「能跑但很慢」，一条 5 秒片可能要十几分钟到半小时以上。
画布「体检」里会显示显存总量与空闲量；低于 12 GB 会标黄并给出这条建议，出片报 OOM 时也会直接告诉你按上面哪几步做。

### 11.0 8 GB 显存能不能跑？能，但要换一套配置（社区实测）

先纠正一个容易犯的错：**别拿「权重加起来 34 GB」去推断 8 GB 跑不了**。社区已经实测跑通，
办法是把两头都缩小，再配 `--lowvram`：

| 角色 | 标准档 | 8 GB 方案 |
|---|---|---|
| 主模型 | `minimax_h3_ref2va_pruned_int8_convrot` 19.5 GB | **`minimax_h3_ref2va_pruned_w4a8_mixed` 11.7 GiB**（[starsfriday/MiniMax-H3-w4a8](https://huggingface.co/starsfriday/MiniMax-H3-w4a8)） |
| 文本编码器 | `qwen3vl_32b_minimax_h3_nvfp4_awq` 14.6 GB | **`qwen3vl_4b_int8_convrot` ~4.9 GB** + ClipProj 矩阵（[ClipProj-MiniMax-H3](https://huggingface.co/NicoLab28/ClipProj-MiniMax-H3)） |
| 启动参数 | 默认 | `--lowvram --fp16-vae`（**不要**加 `--cpu-vae`） |
| 出片参数 | 8 步（画布默认） | 480×864、158 帧、euler + simple |
| 额外节点 | — | [ComfyUI-ClipProj](https://github.com/nicolab28/ComfyUI-ClipProj)（≥0.1.13，提供 `ClipProjApply`） |

实测环境：**RTX 4060 Laptop 8 GB 显存 + 16 GB 内存**，来源
[reventadirecta/MiniMax-H3-ComfyUI-8GB-VRAM](https://github.com/reventadirecta/MiniMax-H3-ComfyUI-8GB-VRAM)（MIT）。

> **实测**：**8 GB 显存 + 32 GB 内存**的机器，`--lowvram --fp16-vae`，
> 用画布「低显存（W4A8 + 4B 编码器）」档跑通：**608×352、5 秒片约 7 分钟**（当时按 20 步测的，
> 现在画布默认 8 步，会更快）。**32 GB 内存就够，不需要 48 GB。**

画布「体检 → 8 GB 显存方案」那一段会把这四个文件的下载链接、存放目录、启动参数、推荐分辨率都列出来；
缺哪个标哪个。装好 `ComfyUI-ClipProj` 节点、三个文件到位后，**在右侧「出片模型档位」选「低显存（W4A8 + 4B 编码器）」**
即可——画布会自动换主模型、换 4B 编码器（type=krea2）、插入 `ClipProjApply` 投影，并把尺寸切到 608×352（横）/ 480×864（竖）。

另外一条老路：`--lowvram` 直接跑标准档（慢，且必须有足够内存）。

## 12. 目录结构（运行后）

```
GuoBaoCanvas\
├── 启动画布.bat / 关闭画布.bat
├── requirements.txt
├── settings.json          ← 首次保存设置后生成（含 API key，别外传，已在 .gitignore）
├── canvas\server.py       ← 画布后端
├── canvas\web\            ← 前端（app.js / index.html / style.css）
├── core\                  ← 构图 / 提示词 / 存储 / 媒体工具
├── steps\                 ← 出片步骤
├── engines\ styles\   ← 引擎参数 / 画风
├── tools\                 ← launch_canvas / stop_canvas / pick_dir
├── projects\              ← 你的集（数据，不进 git）
└── out\                   ← 日志与临时产物（不进 git）
```

---

## 13. 已知限制

- 只有 Windows 启动脚本；其它系统需要自己 `python canvas/server.py --port 8766`。
- 画布主路线是 **ref2va（参考图生成）**；`fl2va` 图生视频要额外 2 个权重（见 7.4）。
- 画布**不提交 GPU 任务时不会占用显卡**；真正出片是 ComfyUI 在跑，关画布不会中断已提交的任务，要停得去 ComfyUI 里取消。
- 模型文件名和默认不同没关系——设置页「高级」里改名字即可。

---

## 附：参考环境

| 项 | 值 |
|---|---|
| 显卡 | NVIDIA GeForce RTX 5090 Laptop，24 GB |
| 驱动 | 621.01 |
| Python | 3.13.11 |
| torch | 2.9.1+cu130（ComfyUI 那边） |
| ComfyUI | 0.42.1 |
| 画布端口 | 8766 |
 