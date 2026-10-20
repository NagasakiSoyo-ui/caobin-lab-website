from pathlib import Path
from html import escape
import json

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'dist'
D = json.loads((ROOT / 'content.json').read_text(encoding='utf-8'))
ROUTES = [('index', '首页', 'Home'), ('research', '研究方向', 'Research'),
          ('publications', '研究成果', 'Research Projects'), ('team', '研究团队', 'Our Team'),
          ('resources', '学习资料', 'Learning Resources'), ('contact', '联系我们', 'Contact')]


def e(value):
    return escape(str(value), quote=True)


def heading(title, english):
    return f'<div class="section-heading"><p class="eyebrow" lang="en">{e(english)}</p><h2>{e(title)}</h2></div>'


def link(href, label):
    return f'<a class="more-link" href="{e(href)}">{e(label)} <span aria-hidden="true">→</span></a>'


def intro(title, english, text, index=''):
    return f'''<header class="page-intro"><div class="container intro-grid">
    <div><p class="breadcrumb"><a href="index.html">首页</a><span>/</span>{e(title)}</p>
    <p class="eyebrow" lang="en">{e(english)}</p><h1>{e(title)}</h1></div>
    <div class="intro-aside"><p class="lead">{e(text)}</p>{index}</div></div></header>'''


def graphic(index):
    drawings = [
        '<path d="M40 42L110 28L175 68L112 109L40 42M110 28L112 109M40 42L37 107L112 109M175 68L183 121L112 109"/>'
        '<circle cx="40" cy="42" r="10"/><circle cx="110" cy="28" r="8"/><circle cx="175" cy="68" r="11"/><circle cx="112" cy="109" r="14"/><circle cx="37" cy="107" r="7"/><circle cx="183" cy="121" r="6"/>',
        '<ellipse cx="110" cy="80" rx="69" ry="49"/><circle cx="88" cy="67" r="15"/><circle cx="133" cy="89" r="21"/><circle cx="68" cy="99" r="7"/><circle cx="143" cy="47" r="6"/><path d="M40 43L28 32M45 111L31 121M176 62L191 58M122 31L125 17"/>',
        '<path d="M52 25C158 25 62 135 168 135M168 25C62 25 158 135 52 135M67 39H153M89 64H131M89 94H131M67 120H153"/><circle cx="110" cy="79" r="14"/>',
        '<rect x="33" y="36" width="58" height="85" rx="4"/><path d="M49 53H75M49 67H75M49 81H65M103 79H145M137 71L145 79L137 87"/><circle cx="174" cy="79" r="27"/><path d="M162 79H186M174 67V91"/>'
    ]
    return f'<svg viewBox="0 0 220 160" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6">{drawings[index]}</svg>'


def project_cards():
    return '<div class="project-grid">' + ''.join(
        f'''<article class="project-card" id="project-{i+1}"><div class="project-art">{graphic(i)}</div>
        <div class="project-copy"><p class="eyebrow">PROJECT {i+1:02}</p><p class="project-program">{e(p['program'])}</p>
        <h3>{e(p['title'])}</h3><dl><div><dt>项目周期</dt><dd>{e(p['dates'])}</dd></div>
        <div><dt>项目编号</dt><dd>{e(p['code'])}</dd></div></dl></div></article>'''
        for i, p in enumerate(D['projects'])) + '</div>'


def resource_card(r):
    search = ' '.join(str(r.get(k, '')) for k in ['title', 'english', 'kind', 'disease', 'year', 'version', 'journal'])
    return f'''<article class="resource-card" data-kind="{e(r['kind'])}" data-disease="{e(r['disease'])}" data-search="{e(search)}">
    <a class="resource-open" href="{e(r['path'])}" target="_blank" rel="noopener" aria-label="阅读：{e(r['title'])}（新窗口打开 PDF）">
    <div class="resource-cover"><img src="{e(r['cover'])}" alt="{e(r['title'])}首页" loading="lazy"><span class="file-label">PDF</span></div>
    <div class="resource-copy"><p class="resource-tags"><span>{e(r['kind'])}</span><span>{e(r['disease'])}</span></p>
    <h3>{e(r['title'])}</h3><p class="resource-version">{e(r['version'])}</p><p class="resource-source">{e(r['journal'])}</p></div></a>
    <div class="resource-actions"><span>{r['pages']} 页 · {r['bytes']/1024/1024:.1f} MB</span>
    <a href="{e(r['path'])}" target="_blank" rel="noopener" aria-label="打开{e(r['title'])}">阅读原文 ↗</a>
    <a href="{e(r['path'])}" download="{e(r['title'])}.pdf" aria-label="下载{e(r['title'])}">下载 ↓</a></div></article>'''


def home():
    return f'''<section class="home-hero"><div class="container hero-grid">
    <div class="hero-copy"><p class="eyebrow">曹彬课题组 · CAO BIN LAB</p>
    <h1>呼吸道感染<br>与临床转化研究</h1><p class="hero-english" lang="en">Respiratory Infection &amp;<br>Translational Research</p>
    <p class="hero-lead">围绕病毒性肺炎、呼吸道病原体、抗病毒药物评价与微生物组，开展临床研究与转化探索。</p>
    <p class="hero-actions"><a class="button primary" href="research.html">研究方向</a><a class="button quiet" href="resources.html">学习资料</a></p></div>
    <figure class="hero-figure"><div class="lab-hero-frame"><img src="{D['leader']['photo']}" alt="曹彬教授学术报告照片" fetchpriority="high"></div>
    <figcaption><span class="portrait-name">曹彬</span><span>{e(D['leader']['role'])}</span></figcaption>
    <p class="hero-footnote">聚焦呼吸系统感染性疾病的临床诊疗与转化研究</p></figure></div></section>
    <section class="home-section home-topics"><div class="container split"><div class="split-head">{heading('研究方向','Research Fields')}{link('research.html','查看完整研究方向')}</div>
    <ol class="theme-list">{''.join(f'<li><a href="research.html#topic-{i+1}"><span class="theme-no">{i+1:02}</span><span class="theme-text"><strong>{e(r["title"])}</strong><span>{e(r["text"].split("；")[0])}</span></span></a></li>' for i,r in enumerate(D['research']))}</ol></div></section>
    <section class="home-section shaded"><div class="container"><div class="row-head">{heading('研究课题','Research Projects')}{link('publications.html','查看科研项目')}</div>{project_cards()}</div></section>
    <section class="home-section"><div class="container leader-feature home-leader-feature"><div class="leader-portrait"><img src="{D['leader']['photo']}" alt="曹彬教授" loading="lazy"></div>
    <div class="leader-text"><p class="eyebrow">GROUP LEADER</p><h2>曹彬 <span lang="en">Bin Cao</span></h2><p class="leader-role">{e(D['leader']['role'])}</p>
    <p class="leader-summary">{e(D['leader']['bio'][0])}</p>{link('team.html','认识研究团队')}</div></div></section>
    <section class="home-section shaded"><div class="container"><div class="row-head">{heading('呼吸疾病学习资料','Learning Resources')}{link('resources.html','全部指南与共识')}</div>
    <p class="section-desc">指南、专家共识与临床学习资料，按疾病方向查阅。</p><div class="resource-grid">{''.join(resource_card(r) for r in D['resources'][:3])}</div></div></section>
    <section class="home-join"><div class="container join-band"><div><p class="eyebrow">CONTACT</p><h2>学术交流与合作</h2></div><div><p>联系人：{e(D['contact']['name'])}</p><a class="contact-mail" href="mailto:{e(D['contact']['email'])}">{e(D['contact']['email'])} ↗</a></div></div></section>'''


def research():
    index = '<ol class="intro-index">' + ''.join(f'<li><a href="#topic-{i+1}"><span>{i+1:02}</span>{e(r["title"])}</a></li>' for i,r in enumerate(D['research'])) + '</ol>'
    return intro('研究方向','Research Fields','围绕呼吸道感染的临床问题，连接病原、宿主与转化研究。', index) + '<div class="container direction-list">' + ''.join(
        f'<article class="direction-row" id="topic-{i+1}"><div><span class="theme-no">{i+1:02}</span><h2>{e(r["title"])}</h2></div><p>{e(r["text"])}</p></article>'
        for i,r in enumerate(D['research'])) + '</div>'


def publications():
    return intro('研究成果','Research Projects & Publications','国家科研项目与研究论文。') + f'''<section class="content-section container">
    {heading('研究课题','Research Projects')}{project_cards()}</section><section class="content-section container" id="papers">
    {heading('研究论文','Publications')}<div class="pending-content"><h3>论文目录整理中</h3><p>待确认论文收录范围后，补充论文题目、作者、期刊及原文链接。</p></div></section>'''


def member_card(p):
    photo = f'<img src="{e(p["photo"])}" alt="{e(p["name"])}" loading="lazy">' if p.get('photo') else f'<span class="portrait-placeholder" aria-label="暂无照片">{e(p["name"])}</span>'
    info = f'<p class="member-stage">{e(p["stage"])}</p>'
    if p.get('school'):
        info += f'<p>{e(p["school"])}</p>'
    if p.get('cohort'):
        cohort = p['cohort']
        if cohort.isdigit():
            cohort += '级'
        info += f'<p class="member-cohort">入学年级：{e(cohort)}</p>'
    if p.get('workplace'):
        info += f'<p class="member-workplace">{e(p["workplace"])}</p>'
    return f'<article class="member-card" data-member="{e(p["id"])}"><div class="member-photo">{photo}</div><div class="member-info"><h3>{e(p["name"])}</h3>{info}</div></article>'


def team():
    jumps = '<nav class="team-jump" aria-label="团队分组">' + ''.join(f'<a href="#{i}">{cn}</a>' for i,cn in [('leader','课题组负责人'),('faculty','团队骨干'),('postdocs','博士后'),('students','在读研究生'),('alumni','已毕业成员')]) + '</nav>'
    result = intro('研究团队','Our Team','',jumps)
    result += f'''<section class="leader-profile shaded" id="leader"><div class="container profile-grid"><figure><img src="{D['leader']['photo']}" alt="曹彬教授"><figcaption>曹彬 · {e(D['leader']['role'])}</figcaption></figure>
    <div><p class="eyebrow">GROUP LEADER</p><h2>曹彬 <span>Bin Cao</span></h2><p class="profile-role">{e(D['leader']['role'])}</p><div class="leader-bio">{''.join(f'<p>{e(p)}</p>' for p in D['leader']['bio'])}</div></div></div></section>'''
    result += f'<section class="container content-section" id="faculty">{heading("团队骨干","Faculty")}<div class="faculty-list">' + ''.join(
        f'<article><h3>{e(n)}</h3><p>个人介绍待补充</p></article>' for n in D['members']) + '</div></section>'
    for group,cn,en in [('postdocs','博士后','Postdoctoral Researchers'),('students','在读研究生','Graduate Students'),('alumni','已毕业成员','Alumni')]:
        people = [p for p in D.get('trainees',[]) if p['group']==group]
        result += f'<section class="container content-section" id="{group}">{heading(cn,en)}<div class="trainee-grid">' + ''.join(member_card(p) for p in people) + '</div></section>'
    return result


def resources():
    options = lambda items: ''.join(f'<option value="{e(s)}">{e(s)}</option>' for s in items)
    return intro('学习资料','Learning Resources','常见呼吸疾病的指南、专家共识与学习资料。点击卡片阅读 PDF，也可下载保存。') + f'''<section class="container content-section resource-section">
    <form id="resource-filters" role="search" aria-label="检索学习资料"><label class="search-field">检索资料<input type="search" id="resource-search" placeholder="搜索标题、疾病或年份" autocomplete="off"></label>
    <label>资料类型<select id="resource-kind"><option value="">全部类型</option>{options(['指南','专家共识','指南摘要'])}</select></label>
    <label>疾病方向<select id="resource-disease"><option value="">全部方向</option>{options(['呼吸道感染','慢阻肺','支气管扩张','哮喘'])}</select></label>
    <button type="reset" class="button quiet">重置</button></form>
    <div class="resource-count"><p id="result-count" role="status" aria-live="polite">共 {len(D['resources'])} 份资料</p><span>按发表年份排列</span></div>
    <div class="resource-grid" id="resource-grid">{''.join(resource_card(r) for r in D['resources'])}</div>
    <div id="resource-empty" class="pending-content" hidden><h2>没有找到匹配资料</h2><p>请尝试其他关键词，或清除分类条件。</p><button type="button" class="more-link" id="clear-filters">清除筛选</button></div>
    <noscript><p>筛选功能需要 JavaScript；所有资料均可直接打开。</p></noscript></section>'''


def contact():
    return intro('联系我们','Contact','欢迎开展呼吸道感染与临床转化研究相关的学术交流。') + f'''<section class="container content-section contact-section">
    <div>{heading('学术交流','Academic Enquiries')}<p>联系人：{e(D['contact']['name'])}</p><a class="contact-address" href="mailto:{e(D['contact']['email'])}">{e(D['contact']['email'])} <span>↗</span></a>
    <p class="contact-tip">点击邮箱地址，可通过您的邮件应用发送邮件。</p></div><aside><p class="eyebrow">EXPLORE</p><h2>了解我们的研究</h2>{link('research.html','研究方向')}{link('team.html','研究团队')}{link('resources.html','学习资料')}</aside></section>'''


def page(route, title, body):
    nav = ''.join(f'<a href="{slug}.html"'+(' aria-current="page"' if slug==route else '')+f'><span>{cn}</span><small lang="en">{en}</small></a>' for slug,cn,en in ROUTES)
    footerlinks = ''.join(f'<a href="{slug}.html">{cn}</a>' for slug,cn,_ in ROUTES[1:])
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{title} · 曹彬课题组</title><meta name="description" content="曹彬课题组：呼吸道感染与临床转化研究。研究方向、科研项目、团队成员与呼吸疾病学习资料。">
    <link rel="stylesheet" href="assets/theme.css"><link rel="stylesheet" href="assets/base.css"><link rel="stylesheet" href="assets/site.css"><script src="assets/site.js" defer></script></head>
    <body data-page="{route}"><a class="skip-link" href="#main">跳至正文</a><header class="site-header"><div class="container masthead">
    <a class="brand" href="index.html"><span class="brand-name">曹彬课题组</span><span class="brand-inst">呼吸道感染与临床转化研究</span></a>
    <button class="menu-toggle" type="button" aria-expanded="false" aria-controls="site-nav"><span>菜单</span><span class="menu-bars" aria-hidden="true"></span></button>
    <nav id="site-nav" aria-label="主导航">{nav}</nav></div></header><main id="main" tabindex="-1">{body}</main>
    <footer class="site-footer"><div class="container lab-footer"><div><a class="footer-brand" href="index.html">曹彬课题组</a><p>呼吸道感染与临床转化研究</p><p lang="en">Respiratory Infection &amp; Translational Research</p></div>
    <nav aria-label="页脚导航">{footerlinks}</nav><div><h2>联系我们</h2><p>{e(D['contact']['name'])}</p><a href="mailto:{e(D['contact']['email'])}">{e(D['contact']['email'])}</a></div></div>
    <div class="container footer-note"><span>曹彬课题组</span><span>Research · Education · Collaboration</span></div></footer></body></html>'''


if __name__ == '__main__':
    renderers = dict(index=home, research=research, publications=publications, team=team, resources=resources, contact=contact)
    for slug,cn,_ in ROUTES:
        (OUT / f'{slug}.html').write_text(page(slug,cn,renderers[slug]()),encoding='utf-8')
    (OUT/'打开网站.txt').write_text('曹彬课题组网站\n\n完整解压后双击 index.html 浏览首页。\n学习资料页面提供 PDF 原文阅读与下载，文件已随网站提供。\n若浏览器不支持直接阅读 PDF，请下载后使用 PDF 阅读器打开。\n请整体移动网站文件夹，保留 assets 和 documents 与网页的相对位置。\n',encoding='utf-8-sig')
    print('Built 6 pages with 9 PDF resources and',len(D.get('trainees',[])),'trainee records.')
