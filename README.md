# JLPT 学习站

N5–N1 的单词卡片、汉字、语法讲解和小测验，另有跨级别的辞典（`/dict/`）和语法词典（`/grammar/`）。纯静态站点，结构沿用 eju-* 系列：
`content/` 里写内容，`build.py` 生成页面，`assets/` 放样式和脚本。

## 目录

```
content/n5.py … n1.py   每个级别的单词、汉字、语法、测验题
content/dictionary/    按级别保存的导入词库 JSON
assets/site.css         样式（浅色 / 深色，每个级别一个主色）
assets/app.js           界面切换、间隔重复卡片、测验（无依赖）
build.py                生成 dist/
verify.py               构建并检查内容和站内链接
dist/                   生成的站点，部署的就是这个目录
```

## 构建

只需要 Python 3.8+，没有第三方依赖。

```
python3 build.py        # 生成 dist/
python3 verify.py       # 生成并检查（需要 node 来检查 app.js 语法）
python3 -m http.server -d dist 8000   # 本地预览
```

## 添加内容

在 `content/n?.py` 里往列表追加条目即可，格式见 `n5.py` 开头的注释。

- 例句和题目里的汉字都要注音，写成 `漢字[かんじ]`；`verify.py` 会找出漏掉的。
- 测验题写成 `(题干, 正确选项, [3 个错误选项], 解说)`，选项顺序在页面上会打乱。
- 词义、读音、汉字写法三类题目由单词表和汉字例词自动生成，不用单独写。
- 辞典和语法词典汇总手写内容和导入词库，按五十音排序。词条按写法和读音合并，优先显示手写释义和例句。导入数据用于两个辞典页，学习卡片和测验从各级 `content/n*.py` 取材。
- 句型里有汉字时，要加 `yomi='假名读法'`（如 `p='〜に対して', yomi='にたいして'`），语法词典靠它排序和搜索。

改完后运行 `python3 verify.py`，再把 `content/` 和 `dist/` 一起提交。

## 刷新辞典数据

将 [OpenJLPT](https://github.com/evanclan/OpenJLPT) 的源码解压到本地，并下载和解压 [Tomoshi SQLite 发布包](https://github.com/tomoshi-app/tomoshi-dict-data/releases)。刷新公开词典时，建议每月用最新的上游版本生成数据。

```
python3 import_dictionary.py --openjlpt path/to/OpenJLPT --tomoshi path/to/tomoshi-dict-open.db
python3 verify.py
```

构建只读取本地快照，无需联网。OpenJLPT 提供参考分级与英文语法释义，Tomoshi 提供简体中文词义。缺少中文释义时显示上游英文释义。导入数据和署名详见 [DICTIONARY-SOURCES.txt](DICTIONARY-SOURCES.txt)。

## 部署到 Cloudflare Pages

Pages 地址：[feather0-jlpt.pages.dev](https://feather0-jlpt.pages.dev/)。

仓库里已经提交了构建好的 `dist/`，Cloudflare 不需要运行构建。

1. Cloudflare 控制台 → Workers & Pages → 创建 → Pages → 连接到 Git，选择这个仓库。
2. 构建设置：
   - Framework preset：None
   - Build command：`exit 0`
   - Build output directory：`dist`
3. 保存并部署，之后每次推送到 `main` 都会自动发布。
4. 需要自定义域名时，在项目的 Custom domains 里添加。

## 说明

- 学习记录（卡片进度、测验最好成绩）只存在浏览器的 localStorage 里，不会上传。
- 内容是个人整理的备考资料，与 JLPT 主办机构无关。
