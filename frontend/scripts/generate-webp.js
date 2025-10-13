#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import sharp from 'sharp';

const publicDir = path.resolve(process.cwd(), 'public');
const targets = [
  { input: 'bg-login.jpg', output: 'bg-login.webp', width: 1920, height: 1080, quality: 60 },
];

async function ensureWebp({ input, output, width, height, quality }) {
  const inputPath = path.join(publicDir, input);
  const outputPath = path.join(publicDir, output);
  if (!fs.existsSync(inputPath)) return;
  const statIn = fs.statSync(inputPath);
  const needs = !fs.existsSync(outputPath) || fs.statSync(outputPath).mtimeMs < statIn.mtimeMs;
  if (!needs) return;
  await sharp(inputPath)
    .resize({ width, height, fit: 'inside', withoutEnlargement: true })
    .webp({ quality })
    .toFile(outputPath);
  console.log(`[webp] generated ${output}`);
}

(async () => {
  try {
    for (const t of targets) await ensureWebp(t);
  } catch (e) {
    console.error('[webp] generation failed:', e.message);
    process.exit(0); // Do not block build
  }
})();
