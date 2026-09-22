"""Build the static site: one page per stay from src/page.html + src/stays.json.

Usage:  python tools/build.py
Writes index.html (first stay in "order") and <path>/index.html for the others.
"""
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / 'src' / 'page.html'
DATA = ROOT / 'src' / 'stays.json'
SPEC_REVEAL = ['', ' r2', '', ' r2', ' r3', '']


def esc(value):
    return html.escape(str(value), quote=True).replace('&#x27;', "'")


def script_json(obj, **kw):
    # Safe to embed inside <script>: never allow "</" to close the tag early.
    return json.dumps(obj, ensure_ascii=False, **kw).replace('</', '<\\/')


def rel_link(from_path, to_path):
    depth = from_path.count('/')
    if from_path == to_path:
        return './'
    return ('../' * depth + to_path) or './'


def toggle_html(key, stays, order):
    opts = []
    for k in order:
        s = stays[k]
        current = ' aria-current="page"' if k == key else ''
        opts.append('        <a class="st-opt" href="%s"%s title="%s">%s</a>' % (
            rel_link(stays[key]['path'], s['path']), current, esc(s['name']), esc(s['label'])))
    return ('<nav class="stay-toggle" aria-label="Choose your stay">\n'
            '        <span class="st-pill" aria-hidden="true"></span>\n%s\n      </nav>') % '\n'.join(opts)


def hero_markup(hero):
    img = '<img src="%s" alt="" width="%d" height="%d" fetchpriority="high" decoding="async">' % (esc(hero['src']), hero['w'], hero['h'])
    if not hero.get('portrait'):
        return img
    return ('<picture><source media="(max-width: 979px) and (orientation: portrait)" srcset="%s">%s</picture>'
            % (esc(hero['portrait']), img))


def preload_markup(hero):
    if not hero.get('portrait'):
        return '<link rel="preload" as="image" href="%s" fetchpriority="high">' % esc(hero['src'])
    return ('<link rel="preload" as="image" href="%s" media="(max-width: 979px) and (orientation: portrait)" fetchpriority="high">\n'
            '<link rel="preload" as="image" href="%s" media="(min-width: 980px), (orientation: landscape)" fetchpriority="high">'
            % (esc(hero['portrait']), esc(hero['src'])))


def hero_vars(hero):
    box, pbox, fbox = hero['box'], hero.get('portraitBox', hero['box']), hero.get('frameBox', hero['box'])
    css = ('--hero-w:%s;--hero-h:%s;--hero-pos:%s;--hero-pw:%s;--hero-ph:%s;--hero-ppos:%s;'
           '--frame-w:%s;--frame-h:%s;--frame-pos:%s') % (
        box[0], box[1], hero['pos'], pbox[0], pbox[1], hero.get('portraitPos', hero['pos']),
        fbox[0], fbox[1], hero.get('framePos', hero['pos']))
    if hero.get('chip1Top'):
        css += ';--chip1-top:%s' % hero['chip1Top']
    return css


def specs_html(stay):
    hl = stay['highlight']
    out = ['      <article class="spec hl glass reveal">',
           '        <div class="stat" aria-hidden="true"><b>%s</b><span>%s</span></div>' % (esc(hl['stat']), esc(hl['statLabel'])),
           '        <div>',
           '          <h3>%s</h3>' % esc(hl['title']),
           '          <p>%s</p>' % esc(hl['text']),
           '        </div>',
           '      </article>']
    for i, (icon, title, text) in enumerate(stay['specs']):
        out += ['      <article class="spec glass reveal%s">' % SPEC_REVEAL[i % len(SPEC_REVEAL)],
                '        <span class="ic"><bm-icon name="%s"></bm-icon></span>' % esc(icon),
                '        <div><h3>%s</h3><p>%s</p></div>' % (esc(title), esc(text)),
                '      </article>']
    return '\n'.join(out)


def localize(stay, depth, base):
    """Photos stored in this repo (paths starting with assets/) are made page-relative;
    share and search images must be absolute URLs."""
    stay = json.loads(json.dumps(stay))
    rel = lambda v: ('../' * depth + v) if isinstance(v, str) and v.startswith('assets/') else v
    absu = lambda v: (base + v) if isinstance(v, str) and v.startswith('assets/') else v
    for k in ('src', 'frameSrc', 'portrait'):
        if k in stay['hero']:
            stay['hero'][k] = rel(stay['hero'][k])
    for p in stay['photos']:
        p['src'], p['thumb'] = rel(p['src']), rel(p.get('thumb'))
        if p['thumb'] is None:
            del p['thumb']
    stay['seo']['image'] = absu(stay['seo']['image'])
    stay['ld']['image'] = absu(stay['ld']['image'])
    return stay


def context(key, data):
    stays, order = data['stays'], data['order']
    stay = localize(stays[key], stays[key]['path'].count('/'), data['base'])
    c = stay['contact']
    ld = dict(stay['ld'])
    ld = {k: ld[k] for k in ld if k in ('@context', '@type', 'name', 'description')} | \
         {'url': data['base'] + stay['path']} | {k: v for k, v in ld.items() if k not in ('@context', '@type', 'name', 'description')}
    return dict(stay,
        key=key,
        url=data['base'] + stay['path'],
        links={'tel': 'tel:' + c['tel'],
               'wa': 'https://wa.me/%s?text=%s' % (c['wa'], quote(c['waMessage'], safe='')),
               'maps': stay['maps']},
        heroVars=hero_vars(stay['hero']),
        heroPicture=hero_markup(stay['hero']),
        preload=preload_markup(stay['hero']),
        prefetch='\n'.join('<link rel="prefetch" href="%s">' % rel_link(stay['path'], stays[k]['path']) for k in order if k != key),
        # Browsers that support it render the other stay in the background on hover/touch, so the switch is instant.
        speculation='<script type="speculationrules">\n%s\n</script>' % script_json({'prerender': [{
            'source': 'list',
            'urls': [rel_link(stay['path'], stays[k]['path']) for k in order if k != key],
            'eagerness': 'moderate'}]}),
        ld=script_json(ld, indent=2),
        toggle=toggle_html(key, stays, order),
        facts='\n'.join('        <li><bm-icon name="%s"></bm-icon>%s</li>' % (esc(i), esc(t)) for i, t in stay['facts']),
        specs=specs_html(stay),
        filters='\n'.join('        <button class="filter-btn%s" role="tab" aria-selected="%s" data-filter="%s">%s</button>' % (
            ' active' if n == 0 else '', 'true' if n == 0 else 'false', esc(f), esc(label))
            for n, (f, label) in enumerate(stay['filters'])),
        catJson=script_json(stay['categories']),
        photosJson=script_json(stay['photos']),
    )


def lookup(ctx, path):
    value = ctx
    for part in path.split('.'):
        if not isinstance(value, dict) or part not in value:
            raise KeyError('Missing value for {{%s}}' % path)
        value = value[part]
    return value


def render(template, ctx):
    def sub(m):
        raw, path = m.group(1) == '&', m.group(2)
        value = lookup(ctx, path)
        return str(value) if raw else esc(value)
    out = re.sub(r'\{\{(&?)([\w.]+)\}\}', sub, template)
    leftover = re.findall(r'\{\{[^}]*\}\}', out)
    if leftover:
        raise ValueError('Unresolved placeholders: %s' % leftover[:5])
    return out


def main():
    data = json.loads(DATA.read_text(encoding='utf-8'))
    template = TEMPLATE.read_text(encoding='utf-8')
    for key in data['order']:
        stay = data['stays'][key]
        out_path = ROOT / stay['path'] / 'index.html'
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(render(template, context(key, data)), encoding='utf-8', newline='\n')
        print('built', out_path.relative_to(ROOT))


if __name__ == '__main__':
    sys.exit(main())
