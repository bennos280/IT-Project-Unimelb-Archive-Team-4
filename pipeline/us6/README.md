# US6 — integrated with the supplied pipeline

## 本次交付

基于本次提供的 pipeline 主入口 `run.py`、transcription `run (4).py`、prompt.txt、
main/coded/notes 模板完成 US6 接入。此前假定的 Page 3 schema 已替换成真实模板字段。
此包在仓库根目录展开，包含 **修改后的完整 pipeline/run.py** 和 **完整 pipeline/us6/**。
在你自己的 US6 branch 上加入这些文件，交由团队测试、review 后再 merge。

修改前请核对当前仓库 pipeline/run.py 与你上传的版本是否一致；如果已有他人更新，
请应用包内 `pipeline_run_us6.patch` 的小范围变更，而不是用旧版本覆盖他们的更改。
新增目录位置与 branch 独立；在 US6 branch 下放 pipeline/us6/ 不会修改 main branch。

## 已确认的上游流程

你提供的主入口是 split → identify → optional preprocess → transcribe → group。
transcribe 返回 dict，并保存到 run.out/transcribe/<page>.json；group 从该 JSON 读取
number_of_dwelling，给 run.pages 中的 page 写 survey ID。

US6 已加在 group 后面，读取同一 survey 的 transcript paths，核验 main/coded 数据，
不调用 OCR、模型、图像识别或付费转录，不修改源 transcript JSON。
notes 和 engine/model/effort/seconds 元数据保留，不参与字段数值比较。
识别模型、fingerprint、weights、preprocess、prompt、score 均未修改，不用重新训练。

## 运行方式

### 现有文件入口（现在就能独立测试）

- 单份 survey 两页输出：
  `python pipeline/us6/run_validation.py --main path/to/main.json --coded path/to/coded.json --survey-id survey-001 --output-dir us6_outputs`
- 本包模拟完整 survey：
  `python pipeline/us6/run_validation.py pipeline/us6/example_survey.json --output-dir us6_outputs`
- 已完成 group 的现有 run：
  `survey validate path/to/output/manifest.json`
- 不依赖 survey 命令安装的同等入口：
  `python pipeline/us6/pipeline_step.py path/to/output/manifest.json`

manifest 入口复用之前保存的转录与 survey 分组，不重新跑付费步骤。
先执行完 group，manifest 中每张 page 必须已有 survey ID 与 transcript 相对路径。

### 连续 pipeline

原来的 `survey <input> --transcribe` 现在在 group 后自动执行 validate。
没有 --transcribe 时不会添加 group/validate，因此不改变免费识别/预处理行为。
已有 run 的 completion 检查现在包含 validate；需要仅验证旧 run 时用上面的 validate 子命令，
避免为了增加 US6 而重新运行前面图像步骤。

### 直接函数调用（不经中间 JSON 文件）

`from pipeline.us6 import validate_survey`

`result = validate_survey(main_dict, coded_dict, notes=notes_dict, survey_id=record_id)`

函数不写文件、不修改传入 dict。上游转录函数本来就返回 dict，因此以后可以在 survey 分组
已经确定、两页 dict 齐全时直接调用；**当前主 pipeline 仍沿用其文件缓存机制**，
因为 step_group 自己也从 transcript 文件读取 dwelling number。
本次没有为去掉中间文件而重写整个 group 或缓存逻辑。

## 输出

直接两页/完整 survey CLI：输出目录里生成 output_flagged.json、output_flags_only.json。
完整结果保持 main/coded/notes 原结构，增加 has_flags、validation_flags、review_statuses；
受影响原字段加 `_flag` 和 `_review_status: ToBeReviewed`。
简化结果只保留 survey_id 和 flags，每条说明类型、原因、涉及字段及原值。

pipeline/manifest 模式：输出到 run.out/validation/ 下相同两个文件，按 survey 汇总，
并带 completed/partial、validated_surveys、skipped_surveys、surveys_with_flags。
未验证的 survey 单独列在 not_validated；**未验证不等于无冲突**。
page_files 把 main/coded 数据关联到原始图像文件名；review.json 增加 step=validate 的复核记录。
manifest pages 记录 validation 状态和结果文件。先前 identify/group/preprocess review 保留。
重复执行 validation 会替换旧的 validate review，不重复堆积。

## 本次主要修正

1. 实际 coded 字段：number_5_to_10、number_over_10_m/f、boarders、participating_members、
   adult_m_breadwinners、adult_f_breadwinners、juvenile_breadwinners_under_21、
   retired_and_indep_persons，以及 children_of_h_or_wife_living/dead/total；不再用旧模拟嵌套字段。
2. 根据 prompt，main.number_of_dwelling 是左上角手写编号；main.number 不作为替代值。
   dwelling number 接受 flat letter，024 a ↔ 24A 一致，24A ↔ 24B 冲突。
3. Resident populated 列按 relationship/age/earning_status 判断；不把职业栏孤立内容或
   annotations、engine/model 等元数据当一名居民。
4. 保留年龄推导：8/7 岁两名儿童对应 children_under_14=2；未知年龄不作 0。
5. main 右侧显式 industry_of_head_code、occupation_of_head_code 与 coded 的
   industry_of_head、occupation_of_head 直接核验同类 code；**不是把职业文字猜成代码**。
   已提供这类源字段而对应值单侧为空仍 flag；旧格式未提供 margin 字段时不假造比较源。
6. 上一步转录输出、schema、状态原路径对齐；接入实际 group/Run.save/review 结构。
7. 新增独立 manifest 验证入口，便于在自己的 branch 测试已生成的 JSON。

## 保留的 US6 规则

跨页：dwelling number、bedrooms/living rooms/unused rooms/sleepouts、residence duration、
resident total、under5/5–10/under14、可明确确定性别的 over10 M/F、唯一 Head 年龄、boarders、
probable house age 的明确范围/边界、居民 sons/daughters 与 living/elsewhere 子女数量的下界关系。

Page 3：living+dead=total；年龄组之和=居民总数；breadwinner categories≤居民总数；
明确居民子群≤居民总数；under5+5–10≤under14；房间子数≤总房间数；
separate bedrooms+living rooms≤总房间数；elsewhere children≤living children。

Page 1：living rooms used as bedrooms=Yes 但 living rooms=0 的冲突。

每条 flag 明确区分 Page 1–3 conflict、Page 1/Page 3 internal conflict、comparison incomplete。
已确认关联的对应值一侧缺失/空白/`/`/`[?]` 仍 flag；两边均无值才跳过直接比较。
没有可验证关系的孤立内容和孤立 `[?]` 不 flag。不会给出自动修正值。

## 未添加与限制

- **多 main sheet / 多 coded card**：实际 step_group 支持同一 survey 多张 main sheet。
  当前 US6 sheet adapter 只处理一张 main 配一张 coded；其它数量报告 NotValidated/partial，
  不丢掉第二张 sheet、不默默挑一张、不盲目把两页 residents 拼接。
  要支持完整 multi-sheet survey，需确认续表居民去重、重复 header 的合并与缺值规则。
- **Codebook**：仍未提供。不猜 municipality=2 是否代表 Page 1 的 Essendon，
  不做 coded 全字段允许值范围验证，也不把 dwelling/structure/tenure/kitchen 等 prose
  直接映射成数字代码。显式 margin code 的同 code 比较已做，不依赖文字映射。
- **other_children 数组**：transcription.schema_for() 证明空模板数组的元素为 string/null，
  但未说明一个条目是每名子女、数量、年龄还是一段原始文字。因此保留内容，有数据则说明
  未做精确计数，不用数组长度假造 died/living_elsewhere 人数。
  旧 uppercase fixture 的唯一 Head OTHER CHILDREN 数值比较仍只作用于旧输入格式。
- **收入/租金**：prompt 要求原样保留货币。不猜 pounds/shillings/pence 与 coded 数字
  单位；未加 normal income - rent = available income 等未确认算式。
- **Head/性别**：Head 不代表男性；首列 Wife 不自动指定为 Head。
  main 模板本身没有 sex/gender 字段，因此 over10 M/F 中 Head 的性别不明确会说明比较不完整。
  不通过 sex_of_head 数字代码擅自补性别。
- **年龄/房间定义**：5–10 按含 5 和 10；under14 不含 14。房间规则假定 separate bedrooms
  与 living rooms 为不同物理房间，不强行加入 kitchen/sleepout 求精确总数；需最终 codebook 确认。
- **Notes**：按之前要求不参与 value 匹配，notes schema 也没有 dwelling number 字段。
- **Survey grouping**：直接复用当前 group 的 survey ID；不重做上游分类与 bundling。
  group 提示的问题会保留，US6 不承诺替代它。

## 测试及证据范围

`python -m unittest discover -s pipeline/us6 -v`

47 项测试通过，覆盖规则、真实 main/coded schema、flat-letter identifiers、margin codes、
原字段状态、cached manifest、缺页/缺 transcript、多 main sheet、不重复 review。
此外使用你上传的真实 step_group 和修改后的 run.py，执行了
step_group → STEPS['validate'] → Run.save → main(['validate', manifest]) 的模拟数据流程。

这证明**已提供代码之间的 US6 接口路径能跑通**；未调用付费 transcription、未重跑真实扫描
识别/预处理/模型转录，也没有访问完整远程仓库或运行其所有 CI。
尚无真实已填写成套 survey transcript 供验证真实数据行为，不把模拟联调称为全仓库验收。


## 2026-10-06 Windows 测试编码修复

已将 test_pipeline.py、test_integration.py、test_rules.py 内全部文本文件读写显式设为 UTF-8。此前 Windows 使用 GBK 默认编码读取包含 Page 1–3 等字符的 review.json，会导致幂等性测试报 UnicodeDecodeError。业务模块原已显式使用 UTF-8，本次没有修改 flag 条件、输出结构或 pipeline/run.py。

验证：47 项测试在常规环境及模拟默认 GBK 的文件读取环境中均通过。模拟检查不等同于在 Windows 机器上实测；请替换后在本地重新运行 python -m unittest discover -s pipeline/us6 -v。真实 survey 和团队完整 pipeline 的测试仍需进行。
