// Usage: node check_es3.js file.jsx
// Parses the file as ECMAScript 3 (acorn) and rejects ES5+ library APIs that
// ExtendScript does not have, since acorn only checks syntax.
"use strict";
const fs = require("fs");
const acorn = require("acorn");
const walk = require("acorn-walk");

const BANNED_MEMBERS = new Set([
  "forEach", "map", "filter", "reduce", "reduceRight", "some", "every", "indexOf", "lastIndexOf",
  "trim", "trimStart", "trimEnd", "bind", "keys", "isArray", "create", "defineProperty",
  "getPrototypeOf", "freeze", "includes", "startsWith", "endsWith", "repeat", "padStart", "find",
  "findIndex", "assign", "now", "toISOString",
]);
const BANNED_GLOBALS = new Set(["JSON", "Promise", "Map", "Set", "Symbol", "WeakMap"]);

const file = process.argv[2];
const src = fs.readFileSync(file, "utf8");
const problems = [];
let ast;
try {
  ast = acorn.parse(src, { ecmaVersion: 3, sourceType: "script", locations: true, allowReturnOutsideFunction: false });
} catch (e) {
  console.error(`${file}: ES3 syntax error: ${e.message}`);
  process.exit(1);
}
walk.full(ast, (node) => {
  if (node.type === "MemberExpression" && !node.computed && BANNED_MEMBERS.has(node.property.name)) {
    problems.push(`line ${node.loc.start.line}: .${node.property.name} is not available in ExtendScript (ES3)`);
  }
  if (node.type === "Identifier" && BANNED_GLOBALS.has(node.name)) {
    problems.push(`line ${node.loc.start.line}: ${node.name} is not available in ExtendScript (ES3)`);
  }
});
if (problems.length) {
  console.error(problems.join("\n"));
  process.exit(1);
}
console.log("ok");
