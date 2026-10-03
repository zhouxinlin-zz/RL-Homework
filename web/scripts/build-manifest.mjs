import { createHash } from "node:crypto";
import { readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../..",
);
const text = new Set([
  ".ts",
  ".tsx",
  ".js",
  ".mjs",
  ".css",
  ".json",
  ".html",
  ".svg",
  ".md",
  ".txt",
  ".yml",
  ".yaml",
]);
async function walk(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const groups = await Promise.all(
    entries.map((entry) =>
      entry.isDirectory()
        ? walk(path.join(directory, entry.name))
        : [path.join(directory, entry.name)],
    ),
  );
  return groups.flat();
}
async function snapshot(files) {
  const entries = await Promise.all(
    files.sort().map(async (file) => {
      const bytes = await readFile(file);
      const content = text.has(path.extname(file).toLowerCase())
        ? bytes.toString("utf8").replaceAll("\r\n", "\n")
        : bytes;
      return [
        path.relative(root, file).split(path.sep).join("/"),
        createHash("sha256").update(content).digest("hex"),
      ];
    }),
  );
  return Object.fromEntries(entries);
}
const inputs = (
  await Promise.all(
    ["src", "public", "scripts"].map((folder) =>
      walk(path.join(root, "web", folder)),
    ),
  )
).flat();
inputs.push(
  ...[
    "package.json",
    "package-lock.json",
    "index.html",
    "vite.config.ts",
    "tsconfig.json",
    "tsconfig.app.json",
    "tsconfig.node.json",
  ].map((file) => path.join(root, "web", file)),
);
const manifestPath = path.join(root, "web/dist/build-info.json");
const outputs = (await walk(path.join(root, "web/dist"))).filter(
  (file) => file !== manifestPath,
);
await writeFile(
  manifestPath,
  JSON.stringify(
    {
      version: 1,
      inputs: await snapshot(inputs),
      outputs: await snapshot(outputs),
    },
    null,
    2,
  ) + "\n",
);
console.log(
  `Verified build manifest: ${inputs.length} inputs, ${outputs.length} outputs.`,
);
