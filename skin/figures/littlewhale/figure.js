/**
 * 小鲸鱼（2026-11-23 月下要的新家形象）。
 *
 * 他的原话：正视着屏幕外，大概就是一个圆，然后两个眼睛，尾巴在后面；
 * 喷水代替跳，走叫游，用不上的动作删掉。
 *
 * 所以：身子是一个圆，两只眼睛在前面对着你（不是侧脸的一只），尾巴藏在身后从左边探出来；
 * 没有腿——kit 给的 `legs` 一根都不画。清单里没有 jump/hop/bow/shiver/flap，
 * 换成一个 `spout`：kit 的自定义动作走 `frame.gesture`，我从头顶的呼吸孔往上喷一股水。
 *
 * 坐标：kit 的 logo 空间（x 0..256，地面 y=256，默认朝右；正视的脸左右对称，翻了也看不出来）。
 */
export function createLittleWhaleBody(base, { kit, host, scheme: startScheme }) {
  const F = kit.f;
  const heartD = kit.heartD;
  const clamp = kit.clamp ?? ((v, a, b) => Math.max(a, Math.min(b, v)));

  /** 四套配色，同一套画法。 */
  const PALETTES = {
    deepseek: { body: '#7C9BF7', fin: '#5B7BEA', belly: '#EAF1FF', line: '#1F2A5C', blush: '#FF8FA3', water: '#8ED0FF' },
    ice: { body: '#DCE9F5', fin: '#B9D2E6', belly: '#FFFFFF', line: '#4A6A85', blush: '#FFB3C0', water: '#9BD8F5' },
    pink: { body: '#F7A8BE', fin: '#EE87A3', belly: '#FFF0F4', line: '#6B2B3E', blush: '#FF6E8E', water: '#9BD8F5' },
    ink: { body: '#5B6376', fin: '#464D5E', belly: '#C9CEDB', line: '#14171F', blush: '#C97A8A', water: '#9BD8F5' },
  };

  let scheme = PALETTES[startScheme] ? startScheme : 'deepseek';
  const pal = (o) => PALETTES[(o && o.acc && o.acc.scheme) || scheme] || PALETTES.deepseek;

  /* 脸的位置，画别的记号时也用这几个数 */
  const EYE = { x: 128, y: 160, gap: 48, r: 20 };   /* x 取身子中线 128，一边一个；原来写 104，整对眼歪在左边 */
  const PUPIL = 9.5;
  const MOUTH = { x: 128, y: 202 };

  /** 一只眼睛。形状按 kit 给的脸来画；默认是一只贴上去的圆眼（白底、深瞳、一个高光）。 */
  function eyeOf(e, cx, cy, k, o, mirror) {
    const dx = (e.dx || 0) * k * mirror, dy = (e.dy || 0) * k;
    cx += dx; cy += dy;
    const rx = (e.rx ?? EYE.r) * k, base = (e.ry ?? EYE.r) * k;
    const shut = clamp((o.blink || 0) + (o.eyeClose || 0), 0, 1);
    const ry = base * (1 - shut * .94);
    const ink = '#2A2233';
    const stroke = `fill="none" stroke="${ink}" stroke-width="${F(7 * k)}" stroke-linecap="round" stroke-linejoin="round"`;
    switch (e.shape) {
      case 'up':
        return `<path ${stroke} d="M${F(cx - rx)} ${F(cy + ry * .3)}Q${F(cx)} ${F(cy - ry * 1.05)} ${F(cx + rx)} ${F(cy + ry * .3)}"/>`;
      case 'down':
        return `<path ${stroke} d="M${F(cx - rx)} ${F(cy - ry * .2)}Q${F(cx)} ${F(cy + ry)} ${F(cx + rx)} ${F(cy - ry * .2)}"/>`;
      case 'lid':
        return ry < 2
          ? `<path ${stroke} d="M${F(cx - rx)} ${F(cy)}L${F(cx + rx)} ${F(cy)}"/>`
          : `<path ${stroke} d="M${F(cx - rx)} ${F(cy)}A${F(rx)} ${F(ry)} 0 0 0 ${F(cx + rx)} ${F(cy)}Z"/>`;
      case 'gt':
        return `<path ${stroke} d="M${F(cx - rx * .55)} ${F(cy - ry)}L${F(cx + rx * .6)} ${F(cy)}L${F(cx - rx * .55)} ${F(cy + ry)}"/>`;
      case 'lt':
        return `<path ${stroke} d="M${F(cx + rx * .55)} ${F(cy - ry)}L${F(cx - rx * .6)} ${F(cy)}L${F(cx + rx * .55)} ${F(cy + ry)}"/>`;
      case 'heart':
        return `<path fill="none" stroke="${ink}" stroke-width="${F(6 * k)}" stroke-linejoin="round" d="${heartD(cx, cy, (e.s || 1) * k)}"/>`;
      case 'spiral': {
        let d = '';
        for (let i = 0; i <= 32; i++) {
          const a = Math.PI * 4.2 * i / 32, r = 1.5 + rx * .9 * i / 32;
          d += (i ? 'L' : 'M') + F(cx + r * Math.cos(a + (e.rot || 0))) + ' ' + F(cy + r * Math.sin(a + (e.rot || 0)));
        }
        return `<path fill="none" stroke="${ink}" stroke-width="${F(3.4 * k)}" stroke-linecap="round" d="${d}"/>`;
      }
    }
    // ring：贴上去的圆眼
    const pr = Math.max(2, base * .48);
    const px = cx + rx * .1 * mirror, py = cy + base * .08;
    return `<g transform="translate(0 ${F(cy)}) scale(1 ${F(clamp(1 - shut * .94, .08, 1))}) translate(0 ${F(-cy)})">` +
      `<ellipse cx="${F(cx)}" cy="${F(cy)}" rx="${F(rx)}" ry="${F(base)}" fill="#FFFFFF" stroke="${ink}" stroke-width="${F(3.6 * k)}"/>` +
      `<circle cx="${F(px)}" cy="${F(py)}" r="${F(pr)}" fill="#1B1524"/>` +
      `<circle cx="${F(px - pr * .34)}" cy="${F(py - pr * .4)}" r="${F(pr * .38)}" fill="#FFFFFF" opacity=".95"/>` +
      `</g>`;
  }

  function draw(petG, fc, o) {
    const t = o.t || 0;
    const p = pal(o);
    const look = o.look || [0, 0];
    const lx = clamp(look[0] || 0, -1, 1), ly = clamp(look[1] || 0, -1, 1);
    const swimming = o.mode === 'walk' || o.mode === 'run';
    const wag = Math.sin(t * (swimming ? 9 : 2)) * (swimming ? 14 : 5);
    const bob = swimming ? Math.sin(t * (o.mode === 'run' ? 12 : 7)) * 3.5 : Math.sin(t * 1.6) * 1.2;
    const g = o.gesture;
    const waving = g && g.kind === 'wave' ? Math.sin(Math.PI * 4 * g.k) : 0;
    const nod = g && g.kind === 'nod' ? Math.sin(Math.PI * 2 * g.k) * 6 : 0;
    const shakeX = g && g.kind === 'shake' ? Math.sin(Math.PI * 4 * g.k) * 7 : 0;
    const danceY = o.mode === 'dance' ? Math.abs(Math.sin(t * 6)) * 5 : 0;
    const dy = bob + nod + danceY;
    const low = (o.low || 0) * .6;

    let s = `<g transform="translate(${F(shakeX)} ${F(dy + low)})">`;

    /* 尾巴：藏在身子后面，从右下角探出来再往上翘，两瓣薄薄的尾叶；游起来摇得快 */
    s += `<g transform="rotate(${F(wag * .7)} 170 250)">` +
      `<path fill="none" stroke="${p.fin}" stroke-width="20" stroke-linecap="round" d="M156 252C176 250 192 244 202 234"/>` +
      `<path fill="${p.fin}" stroke="${p.line}" stroke-width="5" stroke-linejoin="round"` +
      ` d="M200 238C214 218 232 196 248 178C242 202 230 222 220 234C230 238 238 244 244 252C226 252 210 246 200 238Z"/>` +
      `</g>`;

    /* 身子：一个圆 */
    s += `<ellipse cx="128" cy="176" rx="84" ry="78" fill="${p.body}" stroke="${p.line}" stroke-width="6"/>`;
    /* 肚皮 */
    s += `<ellipse cx="128" cy="214" rx="58" ry="32" fill="${p.belly}" opacity=".95"/>`;
    /* 肚皮上的两道褶子 */
    s += `<path fill="none" stroke="${p.line}" stroke-width="2.6" stroke-linecap="round" opacity=".28"` +
      ` d="M104 222Q128 230 152 222M110 234Q128 241 146 234"/>`;

    /* 两边的小鳍；招手那只摆得欢 */
    const finL = -18 + Math.sin(t * 2.6) * 4;
    const finR = 18 - Math.sin(t * 2.6) * 4 - waving * 26;
    s += `<ellipse cx="50" cy="196" rx="24" ry="12" fill="${p.fin}" stroke="${p.line}" stroke-width="4.5"` +
      ` transform="rotate(${F(finL)} 50 196)"/>`;
    s += `<ellipse cx="206" cy="196" rx="24" ry="12" fill="${p.fin}" stroke="${p.line}" stroke-width="4.5"` +
      ` transform="rotate(${F(finR)} 206 196)"/>`;

    /* 腮红 */
    if ((fc.blush || 0) > .02) {
      const a = F(clamp(fc.blush * .85, 0, 1));
      s += `<g opacity="${a}"><ellipse cx="86" cy="192" rx="15" ry="8" fill="${p.blush}"/><ellipse cx="170" cy="192" rx="15" ry="8" fill="${p.blush}"/></g>`;
    }

    /* 头顶的呼吸孔 */
    s += `<ellipse cx="128" cy="106" rx="9" ry="4.5" fill="${p.line}" opacity=".75"/>`;

    /* 嘴：平时一条小弧，说话时张成一个小口 */
    const gap = clamp(((fc.gap && fc.gap[0]) || 50) / 64, .2, 1.2);
    const talkOpen = (o.talk || 0) * gap;
    const mh = 4 + talkOpen * 13;
    s += `<ellipse cx="${MOUTH.x}" cy="${F(MOUTH.y + mh * .35)}" rx="${F(7 + talkOpen * 6)}" ry="${F(mh)}"` +
      ` fill="#5B2233" opacity="${F(.55 + .35 * talkOpen)}"/>`;
    s += `<path fill="none" stroke="${p.line}" stroke-width="4" stroke-linecap="round"` +
      ` d="M${F(MOUTH.x - 13)} ${F(MOUTH.y - 3)}Q${MOUTH.x} ${F(MOUTH.y + 8)} ${F(MOUTH.x + 13)} ${F(MOUTH.y - 3)}"` +
      ` opacity="${F(clamp(1 - talkOpen * 1.6, 0, 1))}"/>`;

    /* 两只眼睛：正对着你 */
    const eL = (fc.eyes && fc.eyes[0]) || { shape: 'ring' };
    const eR = (fc.eyes && fc.eyes[1]) || eL;
    const eyeK = .95;
    s += eyeOf(eL, EYE.x - EYE.gap / 2 + lx * 4, EYE.y + ly * 4, eyeK, o, 1);
    s += eyeOf(eR, EYE.x + EYE.gap / 2 + lx * 4, EYE.y + ly * 4, eyeK, o, -1);

    /* 眉毛 */
    if (fc.brows) {
      const angry = fc.brows === 'angry';
      const y = EYE.y - 34 + ly * 3;
      const left = angry ? `M82 ${F(y - 6)}L112 ${F(y + 3)}` : `M82 ${F(y + 4)}L112 ${F(y - 5)}`;
      const right = angry ? `M174 ${F(y - 6)}L144 ${F(y + 3)}` : `M174 ${F(y + 4)}L144 ${F(y - 5)}`;
      s += `<path fill="none" stroke="${p.line}" stroke-width="5" stroke-linecap="round" d="${left}M${right}"/>`;
    }

    /* 头顶的记号 */
    const mx = 128, my = 74;
    if (fc.sweat) s += `<path fill="${p.water}" transform="translate(190 ${F(116 + 3 * Math.sin(t * 7))})" d="M0 -10C4 -3 7 0 7 4A7 7 0 0 1 -7 4C-7 0 -4 -3 0 -10Z"/>`;
    if (fc.anger) {
      const k = 1 + .12 * Math.sin(t * 10);
      s += `<g transform="translate(${mx + 40} ${F(my + 8)}) scale(${F(k)})" fill="none" stroke="#E5484D" stroke-width="5" stroke-linecap="round">` +
        `<path d="M-10 -3Q-3 -3 -3 -10M3 -10Q3 -3 10 -3M10 3Q3 3 3 10M-3 10Q-3 3 -10 3"/></g>`;
    }
    if (fc.bang) s += `<g transform="translate(${mx} ${F(my - 6)})"><path fill="none" stroke="${p.line}" stroke-width="8" stroke-linecap="round" d="M0 -15V3"/><circle fill="${p.line}" cx="0" cy="14" r="4.5"/></g>`;
    if (fc.question) s += `<g transform="translate(${mx} ${F(my - 6)})"><path fill="none" stroke="${p.line}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" d="M-8 -10Q-8 -20 0 -20Q9 -20 9 -11Q9 -4 0 -1V4"/><circle fill="${p.line}" cx="0" cy="14" r="4.5"/></g>`;
    if (fc.sparkle) {
      const k = .85 + .25 * Math.sin(t * 7);
      s += `<g stroke="#FFFFFF" stroke-width="3.4" stroke-linecap="round" opacity=".95">` +
        `<path transform="translate(128 132) scale(${F(k)})" d="M-8 0H8M0 -8V8"/>` +
        `<path transform="translate(190 150) scale(${F(k * .8)})" d="M-6 0H6M0 -6V6"/></g>`;
    }
    if (fc.streams) {
      const w = 2 * Math.sin(t * 6);
      s += `<path fill="${p.water}" opacity=".75" d="M96 178Q${F(94 + w)} 204 97 226L105 226Q${F(104 + w)} 204 104 178Z"/>`;
      s += `<path fill="${p.water}" opacity=".75" d="M160 178Q${F(158 + w)} 204 161 226L169 226Q${F(168 + w)} 204 168 178Z"/>`;
    }

    /* 说话时嘴边冒的小泡 */
    if ((o.talk || 0) > .05) {
      for (let i = 0; i < 3; i++) {
        const k = ((t * .8 + i / 3) % 1);
        s += `<circle cx="${F(MOUTH.x + 16 + 7 * Math.sin(k * 6 + i))}" cy="${F(MOUTH.y - 6 - 34 * k)}" r="${F(2 + 2 * i)}"` +
          ` fill="none" stroke="${p.water}" stroke-width="2.6" opacity="${F(.6 * Math.sin(Math.PI * k))}"/>`;
      }
    }

    /* 喷水：代替跳 */
    if (g && g.kind === 'spout') {
      const up = Math.sin(Math.PI * clamp(g.k * 1.1, 0, 1));
      const top = 100 - 120 * up;
      s += `<path d="M123 100C119 ${F(100 - 46 * up)} 126 ${F(100 - 92 * up)} 124 ${F(top)}` +
        `Q128 ${F(top - 9)} 132 ${F(top)}C133 ${F(100 - 92 * up)} 130 ${F(100 - 46 * up)} 133 100Z"` +
        ` fill="${p.water}" opacity="${F(.35 + .5 * up)}"/>`;
      for (let i = 0; i < 5; i++) {
        const a = -Math.PI / 2 + (i - 2) * .5, d = 26 * up;
        s += `<circle cx="${F(128 + Math.cos(a) * d * 1.55)}" cy="${F(top + Math.sin(a) * d - 4)}"` +
          ` r="${F(1.8 + 2.2 * up)}" fill="${p.water}" opacity="${F(.85 * up)}"/>`;
      }
      s += `<ellipse cx="128" cy="252" rx="${F(30 + 26 * up)}" ry="${F(4 + 4 * up)}" fill="none" stroke="${p.water}"` +
        ` stroke-width="3" opacity="${F(.45 * (1 - up * .5))}"/>`;
    }

    s += '</g>';
    if (s !== drawn) { petG.innerHTML = s; drawn = s; }
  }

  let drawn = '';

  return kit.createBody(host, {
    figure: {
      draw,
      setScheme(id) {
        const key = String(id || '').split('-')[0];
        if (PALETTES[key]) scheme = key;
      },
      setSkin(skin) {
        const key = String((skin && skin.scheme) || '').split('-')[0];
        if (PALETTES[key]) scheme = key;
      },
      /* 这几样它自己画，kit 就别再画一遍 */
      gestures: ['nod', 'shake', 'wave'],
      anchors: {
        gaze: [EYE.x, EYE.y],
        tear: [EYE.x, EYE.y + 24],
        tears: [[EYE.x - 22, EYE.y + 22], [EYE.x + 22, EYE.y + 22]],
        z: [188, 88],
        hearts: [70, 190, 118],
        bubble: [128, 60],
      },
      extent: [0, 60, 256, 256],
      hits: [[128, 176, 92]],
    },
    words: {
      spout: { motion: { seconds: 1.6, face: 'happy', sound: 'chirps' } },
    },
  });
}
