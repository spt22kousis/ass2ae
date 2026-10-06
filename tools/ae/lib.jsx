// Shared helpers for the AE test scripts (ES3). Loaded with $.evalFile.
var AETEST = (function () {
    function q(s) {
        s = String(s);
        var out = "\"";
        for (var i = 0; i < s.length; i++) {
            var c = s.charAt(i), code = s.charCodeAt(i);
            if (c === "\"" || c === "\\") { out += "\\" + c; }
            else if (code < 0x20 || code > 0x7e) {
                var h = code.toString(16);
                while (h.length < 4) { h = "0" + h; }
                out += "\\u" + h;
            } else { out += c; }
        }
        return out + "\"";
    }

    function toJson(v, depth) {
        depth = depth || 0;
        if (depth > 12) { return q("<too deep>"); }
        if (v === null || v === undefined) { return "null"; }
        var t = typeof v;
        if (t === "number") { return isFinite(v) ? String(v) : q(String(v)); }
        if (t === "boolean") { return v ? "true" : "false"; }
        if (t === "string") { return q(v); }
        if (t === "function") { return q("<function>"); }
        if (v instanceof Array) {
            var parts = [];
            for (var i = 0; i < v.length; i++) { parts.push(toJson(v[i], depth + 1)); }
            return "[" + parts.join(",") + "]";
        }
        var items = [];
        for (var k in v) {
            if (!v.hasOwnProperty || v.hasOwnProperty(k)) {
                var val;
                try { val = v[k]; } catch (e) { val = "<error " + e.toString() + ">"; }
                items.push(q(k) + ":" + toJson(val, depth + 1));
            }
        }
        return "{" + items.join(",") + "}";
    }

    function writeText(path, text) {
        var f = new File(path);
        f.encoding = "UTF-8";
        if (!f.open("w")) { throw new Error("cannot write " + path + " (enable Preferences > Scripting & Expressions > Allow Scripts to Write Files)"); }
        f.write(text);
        f.close();
    }

    function tree(prop, depth) {
        depth = depth || 0;
        var node = { name: prop.name, matchName: prop.matchName };
        try { node.type = prop.propertyType === PropertyType.PROPERTY ? "prop" : "group"; } catch (e) {}
        if (node.type === "prop") {
            try { node.valueType = prop.propertyValueType; } catch (e1) {}
            try { node.value = prop.value; } catch (e2) {}
            try { if (prop.canSetExpression && prop.expression) { node.expression = prop.expression; node.expressionError = prop.expressionError; } } catch (e3) {}
        } else if (depth < 8) {
            node.children = [];
            for (var i = 1; i <= prop.numProperties; i++) { node.children.push(tree(prop.property(i), depth + 1)); }
        }
        return node;
    }

    function reflectNames(obj, kind) {
        var out = [];
        try {
            var list = obj.reflect[kind];
            for (var i = 0; i < list.length; i++) { out.push(list[i].name); }
        } catch (e) { out.push("<error " + e.toString() + ">"); }
        return out;
    }

    function codes(s) {
        var out = [];
        for (var i = 0; i < s.length; i++) { out.push(s.charCodeAt(i)); }
        return out;
    }

    // saveFrameToPng renders while the script sleeps; a File object caches .exists,
    // so make a fresh one on every poll.
    function waitForFile(path, seconds) {
        for (var i = 0; i < seconds * 10; i++) {
            var f = new File(path);
            if (f.exists && f.length > 0) { return true; }
            $.sleep(100);
        }
        return false;
    }

    return { toJson: toJson, writeText: writeText, tree: tree, reflectNames: reflectNames, codes: codes,
             waitForFile: waitForFile, q: q };
})();
