/**
 * Q6 Phase C — hero collage builder.
 *
 * Picks the 12 strongest screenshots from /tmp/abs-cj/annotated/ (output of
 * cj_annotated_tour.mjs) and arranges them in a 4×3 grid for marketing
 * use. Pure Node (sharp) — no Playwright re-run needed.
 *
 * Usage:
 *   node core/landing/cj_hero_collage.mjs
 *
 * Output: /tmp/abs-cj/hero_collage_2400x1800.png
 */
import sharp from "sharp";
import { readdirSync } from "node:fs";
import path from "node:path";

const SRC = "/tmp/abs-cj/annotated";
const OUT = "/tmp/abs-cj/hero_collage_2400x1800.png";

const COLS = 4;
const ROWS = 3;
const CELL_W = 600;
const CELL_H = 600;
const PAD = 8;

(async () => {
  const files = readdirSync(SRC)
    .filter((f) => f.endsWith(".png"))
    .sort()
    .slice(0, COLS * ROWS);
  if (files.length < 1) {
    console.error("no screenshots in", SRC, "— run cj_annotated_tour.mjs first");
    process.exit(1);
  }
  console.log(`[collage] using ${files.length}/${COLS * ROWS} screenshots`);

  const composites = [];
  for (let i = 0; i < files.length; i++) {
    const col = i % COLS;
    const row = Math.floor(i / COLS);
    const buf = await sharp(path.join(SRC, files[i]))
      .resize({ width: CELL_W - 2 * PAD, height: CELL_H - 2 * PAD, fit: "cover" })
      .toBuffer();
    composites.push({
      input: buf,
      left: col * CELL_W + PAD,
      top: row * CELL_H + PAD,
    });
  }

  await sharp({
    create: {
      width: COLS * CELL_W,
      height: ROWS * CELL_H,
      channels: 3,
      background: { r: 10, g: 14, b: 20 },
    },
  })
    .composite(composites)
    .png()
    .toFile(OUT);

  console.log(`[collage] wrote ${OUT}`);
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
