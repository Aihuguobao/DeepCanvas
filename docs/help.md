# 提示词速查（图片 / 视频）

只放"怎么写"。约束与流程不在这里。

---

# 一、图片提示词

用于 Krea2 出角色图、场景空镜。正文英文，结构按下面四到七项写，缺项就写 `N/A` 也别瞎编。

## 1.1 角色

| 项 | 写什么 | 例 |
|---|---|---|
| 面部 | 脸型、五官特征、左右可核对的标记 | `oval face, single black mole under the right eye` |
| 发型 | 长度、层次、刘海、发色（可带挑染） | `chin-length bob, blunt fringe, silver-white with pink tips` |
| 妆容 | 眼妆、唇色、肤感；不加滤镜词 | `thin winged eyeliner, soft coral lip, natural skin texture` |
| 身材 | 身高、体型、比例，用数字 | `168 cm, slim build, long legs, narrow shoulders` |
| 服装 | 从外到内逐层，带材质和颜色 | `white short-sleeve shirt under navy V-neck knit vest, grey pleated mini skirt` |
| 姿势 | 重心、手脚位置、朝向 | `standing, weight on the left leg, right hand at her side, facing the camera` |

**模板（一条覆盖上面全部）**

```text
A photograph of a 168 cm slim young woman (Chinese, mid-20s) with an oval face,
a single small mole under the right eye, chin-length silver-white bob with blunt
fringe and pink-tipped ends, thin winged eyeliner and coral lip with visible skin
texture, wearing a white short-sleeve shirt under a navy V-neck knit vest, a grey
pleated mini skirt, black knee-high socks and brown leather loafers, standing with
weight on the left leg and the right hand relaxed at her side, facing the camera,
full body from head to feet, plain light grey background, soft even studio light,
natural fabric texture, 35 mm photo, no text, no watermark.
```

> 尾巴只写"构图 + 背景 + 光线"，别混进材质词；材质词交给画风行。

## 1.2 场景

| 项 | 写什么 | 例 |
|---|---|---|
| 场景 | 有什么、怎么排布、左右固定 | `a low bed on the right, a window on the left, a wardrobe against the back wall` |
| 光线 | 光从哪来、软硬、色温 | `soft morning daylight from the window on the left, low contrast` |
| 镜头位置 | 机位高度、焦段、视角 | `chest height, 35 mm lens, straight-on view` |
| 材质 | 表面与磨损 | `oak floorboards, matte painted wall, wrinkled linen duvet` |

**模板**

```text
A photograph of an empty room: a girl's bedroom with a low bed and white duvet on
the right, a window with sheer white curtains on the left, a wooden wardrobe against
the back wall, a small desk and chair under the window, oak floorboards, matte warm
grey walls, wrinkled linen fabric, soft morning daylight entering from the window
on the left, low contrast, chest-height camera with a 35 mm lens, straight-on view,
no people, no figures, no text, no watermark.
```

> 空镜要写"没有人"，但不要描述人；描述人反而会把人生出来。

---

# 二、视频提示词

## 2.0 通用铁律（两类都适用）

1. 一镜一个主动作，最多加一个运镜；动作要写距离和时间预算，不写形容词。
2. 写姿态和重心，不写"奔跑""优雅"这类概括词。
3. 不写否定句——提到什么就会画出什么。
4. 正文英文；中文只留给台词 `<d>`。
5. 定义了 `<Subject N>` 就全程只用它，不混用 she / her。
6. 挂了参考图就别在正文重写长相和衣服；正文只写动作 / 表情 / 镜头 / 声音。
7. 脚要单独交代：赤足写 barefoot，穿鞋写鞋的款式。

## 2.1 首帧参考图出视频（FL2VA）

首帧已经确定画面，所以只写"这一帧之后怎么演"。

| 项 | 写什么 | 例 |
|---|---|---|
| 镜头 | 一个运镜，或固定 | `The camera holds a static shot.` / `The camera tracks sideways at her walking pace.` |
| 动作 | 主动作 + 距离 + 时间 | `She walks three steps to the window within 3 seconds.` |
| 人物表情 | 肌肉层面的变化 | `eyes narrow, jaw tightens, then relaxes` |

**模板**

```text
The camera holds a static shot at chest height. Within the first two seconds she
pushes herself up from the bed, crosses three steps to the window on the left, and
stops with one hand on the sheer curtain. Her eyes narrow as the light hits them,
then her shoulders drop and her jaw relaxes. One continuous take, no cuts.
```

## 2.2 多参考图（Ref2VA，六段式）

六个段落，顺序固定，一段都不能省。

主体定义只写「是谁、来自哪张图」，一行一个主体。参考图里没有的东西（半身图的下半身、容器内部）才需要往后补，写法见 2.2.1。

| 段 | 写什么 |
|---|---|
| `subject_definitions` | 每个主体一行，写明来自哪张图（`in <Picture 1>`），只写"是什么" |
| `summary` | 这一段一句话要发生什么 |
| `retention_analysis` | 每个主体一行：在哪几镜出现、保留到什么程度 |
| `detailed_description` | 风格句 + 逐镜画面、动作、机位、运镜 |
| `overall_soundscape` | 环境声：房间底噪、脚步、布料、鸟叫 |
| `non_diegetic_music` | 配乐；没有就写 `N/A` |

小类与写法：

| 项 | 写什么 | 例 |
|---|---|---|
| 镜头 | 景别 + 机位 + 运镜，一句一个 | `A medium shot at chest height; the camera follows sideways.` |
| 动作 | 主动作写位置变化和时间；一镜只一个 | `She crosses to the wardrobe in three steps, opens the door with her right hand.` |
| 人物表情 | 肌肉动作，不写情绪词 | `brows lift, lips part slightly, eyes stay on the window` |

**模板（整段可抄）**

```text
subject_definitions:
<Subject 1> is the young woman in <Picture 1>.
<Subject 2> is the location in <Picture 2>.

summary:
Segment 2 of five. <Subject 1> rises from the bed, crosses to the window on the left, parts the sheer curtain, and looks out.

retention_analysis:
<Subject 1> (appears in every shot): fully_preserved - face, hair and clothing come from <Picture 1>.
<Subject 2> (appears in every shot): fully_preserved - the space comes from <Picture 2>.

detailed_description:
A soft, quiet, naturalistic style, warm morning light from the left, low contrast. One continuous take, no cuts, the camera following sideways at her walking pace.

<Subject 1> pushes herself up from the bed edge, steps into the room, and walks three steps to the window on the left, her skirt and knee socks catching the sun. She stops, parts the sheer curtain with one hand, leans slightly into the light, and looks out. Her brows lift, then her eyes settle.

overall_soundscape:
Quiet room tone, birdsong near the window, socked steps on the floorboards, the soft slide of the curtain.

non_diegetic_music:
A soft, sparse solo piano at a slow tempo with a little room reverb, very low in the mix.
```

**单场景多分镜（同一个场景拆成多镜）**

场景卡只挂一次（`<Picture 2>`），一集拆成多镜时每镜写一份六段，但只有三样是「每镜换」的，其余照抄：

| 段 | 多镜时怎么写 |
|---|---|
| `subject_definitions` | **整集照抄**。一行一个主体、只写"是谁"；参考图里没有的构型或细节，需要时按 2.2.1 补 |
| `retention_analysis` | **整集照抄**，写 "appears in every shot" |
| `detailed_description` 的风格句 | **整集照抄**，多镜必须同一画风 |
| `summary` | **每镜换**，开头标序号：`Segment 2 of five.` |
| `detailed_description` 的动作部分 | **每镜换**，只写本镜的主动作 |
| `overall_soundscape` | **每镜换**（本镜有什么声音） |

同一篮球馆的两镜，`summary` 对比：

```text
[镜1] Segment 1 of five. <Subject 1> pushes the gym door open, walks three steps onto the court with a ball under her arm, and looks up at the hoop.
[镜2] Segment 2 of five. <Subject 1> dribbles the ball at a quick jog toward the left hoop.
```

**要点**：场景行不换，模型才不会每镜重新编一个球馆；只换动作和声音。场景里不许出现本镜画面外的物件（门、隔壁房间），否则模型会把镜头拖过去。

### 2.2.1 细化主体定义

定义栏默认只写「是谁、来自哪张图」，一句就够：

```
<Subject 1> is the woman in <Picture 1>.
```

但**参考图里没有的内容**，模型会按自己的先验补。要它按你的意思补，就在定义后面接一段细描述。

两类最常遇到：

**人物：参考图看不到的部分**

半身 / 胸像参考图没有下半身，视频里一旦拉到全身，模型就得自己编：

```
<Subject 1> is the woman in <Picture 1>: a long bright red pleated skirt and white canvas sneakers.
```

不写这一句，它会按上衣同色系自己配一条裙子；写清了就是红裙白鞋。

**场景：画面里有、但看不见内部的东西**

```
<Subject 2> is the alley in <Picture 2>: a narrow concrete alley with pale grey walls, a green steel dumpster on the right whose lid is propped open, and the inside of that dumpster is packed full of black refuse bags, flattened cardboard and crumpled paper.
```

不写桶里有什么，桶口就是空的；写了之后镜头一推近，黑袋和纸板就在桶里。

**放哪、怎么放**

- 接在冒号后面，一行一个主体
- 只写参考图里**没有**的东西；图里已经有的（脸、发型、衣服款式）不要复述，文字和图会抢定义权
- 补全的说法要具体到颜色和款式，写「一条裙子」等于没写

## 2.3 对话与台词

台词只写在 `detailed_description` 里，包在 `<d>[语言] …</d>` 中；`overall_soundscape` / `non_diegetic_music` 不重复写台词。

| 项 | 写什么 | 例 |
|---|---|---|
| 说话人 | 参考主体写 `<Subject N> (Sx)`；`(Sx)` 是稳定发声人编号，从 S1 起；不说话的角色不给 ID | `<Subject 1> (S1)` |
| 台词 | 原文语言包在 `<d>` 里 | `<d>[Chinese] 我回来了。</d>` |
| 说话动作 | 先写动作再引台词 | `turns toward the window and says,` |
| 声音 | 音色 / 语气 / 节奏写在 says 前 | `says in a soft sleepy voice with a slow pace,` |
| 画外音 | 固定短语 `says in an off-screen voiceover`，**每个画外音块后面紧跟嘴唇闭合**；人不在画里写 not in frame | `<Subject 1> (S1) says in an off-screen voiceover: <d>[Chinese] 我一直都在。</d> while her lips remain completely closed.` |
| 跨切延续 | 台词跨 `[Shot]` 时**连接处两侧都写** `<scenetrans>`，并明说音频延续 | `<scenetrans> … continues seamlessly across the cut …` |
| 被片尾截断 | 用 `<cutoff>`，只能落在最后一镜 | `… <d>[Chinese] 你别走——</d> <cutoff>` |
| 听不清 | 不猜不转写，写 `[unclear]` | `<d>[Chinese] [unclear]</d>` |

**模板**

```text
<Subject 1> (S1) turns her head toward the window and says in a quiet morning
voice, <d>[Chinese] 今天天气真好。</d> Then she pushes the curtain aside with one hand.
```

> 正文必须英文——正文里写中文会被模型念出来；中文只留给 `<d>`。
> 台词只写在 `detailed_description` 的 `<d>` 里，别在音轨两段重复。

---

# 三、两类常见翻车与改法

| 现象 | 原因 | 改法 |
|---|---|---|
| 动作看着像没动 | 只写动词，没给距离和时间 | 写"几步、几秒内" |
| 人物脸变了 | 正文又重写了外貌，引入新词 | 删掉正文里的长相/衣服描述 |
| 参考图里的场景被抄进画面 | 没点名"只取人物" | `<Subject 1>` 行写明只取人物 |
| 画面多出一个人影 | 用了复数人称或"所有人" | 单人就全用单数 |
| 中文被念出来 | 正文写了中文 | 正文改英文，中文只留 `<d>` |
| 镜头乱漂 | 一镜写了两个运镜 | 只留一个 |
| 镜中镜、乱切 | 时间码写太密 | 一镜一刀足够，间隔 ≥1.5 秒 |
| 镜头莫名被拽向一侧 / 画外多出东西 | 正文写了画面之外的东西（门、窗外、隔壁房间），模型为了让它入镜只能挪镜头 | 只写画面里看得见的；要「走远 / 离开」就停在画面内边界，别描述画外发生的事 |

---

# 四、参数

| 项 | 值 | 说明 |
|---|---|---|
| 出片分辨率 | 竖屏 1088×1920 / 横屏 1920×1088 | 画布按项目比例自动给 |
| 帧数 | 17k+5 档位（124 / 141 / 158…） | 24 fps |
| latent 接续 | 每段开头被吃掉 22 帧 | 想留 4 秒净时长，设定要 +0.92 秒 |
| 步数 | turbo LoRA 8 步；dasiwa v4 LoRA 4 步 | 步数超过 LoRA 训练档会过火 |
| 参考图数量 | Ref2VA 建议 ≤3 张 | 一张图只承担一个职责 |
