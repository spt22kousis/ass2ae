// Probe the After Effects scripting APIs ass2ae depends on.
// Writes tools/ae/out/probe_api.json and probe_textindex.png, then removes its comps.
(function () {
    var here = File($.fileName).parent;            // tools/ae/probes
    var outDir = here.parent.fsName + "/out";
    $.evalFile(here.parent.fsName + "/lib.jsx");
    var T = AETEST;
    var R = {};
    var made = [];
    var keepComps = [];  // needed until the asynchronous frame render is done

    function section(name, fn) {
        try { R[name] = fn(); } catch (e) { R[name] = { error: e.toString(), line: e.line }; }
    }
    function textDoc(layer) { return layer.property("ADBE Text Properties").property("ADBE Text Document"); }
    function newComp(name, dur) {
        var c = app.project.items.addComp(name, 1920, 1080, 1, dur || 10, 24000 / 1001);
        made.push(c);
        return c;
    }
    function addAnimator(layer, color, amountExpr) {
        var anims = layer.property("ADBE Text Properties").property("ADBE Text Animators");
        var a = anims.addProperty("ADBE Text Animator");
        var idx = a.propertyIndex;
        function A() { return layer.property("ADBE Text Properties").property("ADBE Text Animators").property(idx); }
        A().property("ADBE Text Animator Properties").addProperty("ADBE Text Fill Color");
        A().property("ADBE Text Animator Properties").property("ADBE Text Fill Color").setValue(color);
        var sels = A().property("ADBE Text Selectors");
        for (var i = sels.numProperties; i >= 1; i--) {
            if (sels.property(i).matchName !== "ADBE Text Expressible Selector") { sels.property(i).remove(); }
        }
        A().property("ADBE Text Selectors").addProperty("ADBE Text Expressible Selector");
        var sel = A().property("ADBE Text Selectors").property("ADBE Text Expressible Selector");
        sel.property("ADBE Text Range Type2").setValue(1);
        sel.property("ADBE Text Expressible Amount").expression = amountExpr;
        return sel.property("ADBE Text Expressible Amount");
    }
    function bigText(comp, text, y) {
        var l = comp.layers.addText(text);
        var p = textDoc(l), td = p.value;
        td.resetCharStyle();
        td.font = "ArialMT";
        td.fontSize = 110;
        td.applyFill = true;
        td.fillColor = [1, 1, 1];
        td.applyStroke = false;
        td.justification = ParagraphJustification.LEFT_JUSTIFY;
        p.setValue(td);
        l.property("ADBE Transform Group").property("ADBE Position").setValue([60, y]);
        return l;
    }

    section("app", function () {
        return { version: app.version, buildName: app.buildName, language: app.isoLanguage,
                 exprEngine: app.project.expressionEngine, extendscript: $.version };
    });

    var comp = newComp("ass2ae_probe");

    section("comp", function () {
        return { frameRate: comp.frameRate, frameDuration: comp.frameDuration,
                 exactNtsc: comp.frameRate === 24000 / 1001, frameDurationTimes1001: comp.frameDuration * 24000 };
    });

    section("newline", function () {
        var a = comp.layers.addText("AB\rCD");
        var b = comp.layers.addText("AB\nCD");
        var c = comp.layers.addText("AB\u0003CD");
        return { cr: T.codes(textDoc(a).value.text), lf: T.codes(textDoc(b).value.text),
                 etx: T.codes(textDoc(c).value.text) };
    });

    section("textDocument", function () {
        var l = comp.layers.addText("AB\rCDE");
        var td = textDoc(l).value;
        var out = { props: T.reflectNames(td, "properties"), methods: T.reflectNames(td, "methods") };
        var keys = ["font", "fontFamily", "fontStyle", "fontLocation", "fontSize", "leading", "autoLeading",
                    "tracking", "horizontalScale", "verticalScale", "baselineLocs", "baselineShift", "justification",
                    "strokeOverFill", "applyStroke", "applyFill", "fillColor", "fauxBold", "lineJustification"];
        for (var i = 0; i < keys.length; i++) {
            try { out[keys[i]] = td[keys[i]]; } catch (e) { out[keys[i]] = "<error " + e.toString() + ">"; }
        }
        out.rect = l.sourceRectAtTime(0, false);
        out.rectExtents = l.sourceRectAtTime(0, true);
        // can scales / leading be written?
        try {
            td.horizontalScale = 1.5; td.verticalScale = 0.5; td.autoLeading = false; td.leading = 200;
            textDoc(l).setValue(td);
            var back = textDoc(l).value;
            out.writeBack = { horizontalScale: back.horizontalScale, verticalScale: back.verticalScale,
                              autoLeading: back.autoLeading, leading: back.leading, baselineLocs: back.baselineLocs };
        } catch (e) { out.writeBack = "<error " + e.toString() + ">"; }
        return out;
    });

    section("animator", function () {
        var l = comp.layers.addText("ABCD");
        var anims = l.property("ADBE Text Properties").property("ADBE Text Animators");
        var a = anims.addProperty("ADBE Text Animator");
        var out = { afterAdd: T.tree(a) };
        var idx = a.propertyIndex;
        var A = l.property("ADBE Text Properties").property("ADBE Text Animators").property(idx);
        A.property("ADBE Text Selectors").addProperty("ADBE Text Expressible Selector");
        A = l.property("ADBE Text Properties").property("ADBE Text Animators").property(idx);
        A.property("ADBE Text Animator Properties").addProperty("ADBE Text Fill Color");
        A = l.property("ADBE Text Properties").property("ADBE Text Animators").property(idx);
        out.full = T.tree(A);
        var basedOn = A.property("ADBE Text Selectors").property("ADBE Text Expressible Selector").property("ADBE Text Range Type2");
        out.basedOnValues = [];
        for (var v = 1; v <= 4; v++) {
            try { basedOn.setValue(v); out.basedOnValues.push(basedOn.value); } catch (e) { out.basedOnValues.push("<error " + e.toString() + ">"); }
        }
        try { out.basedOnCaption = basedOn.propertyParameters; } catch (e2) {}
        return out;
    });

    section("markers", function () {
        var l = comp.layers.addText("ABCD");
        var mk = l.property("ADBE Marker");
        var mv = new MarkerValue("AB");
        mv.duration = 1 / 3;
        var setOk;
        try { mv.setParameters({ kind: "k,k", cs: "8,12", num: 5, furi: "[[\"あ\",1.5,0.08,\"<\"]]" }); setOk = true; } catch (e) { setOk = e.toString(); }
        mk.setValueAtTime(1.2345678, mv);
        var mv2 = new MarkerValue("CD");
        mv2.duration = 0.25;
        mk.setValueAtTime(2.5, mv2);
        var back = mk.keyValue(1);
        var params = back.getParameters();
        var types = {};
        for (var k in params) { types[k] = typeof params[k]; }
        return { setParameters: setOk, time: mk.keyTime(1), timeDelta: mk.keyTime(1) - 1.2345678,
                 duration: back.duration, durationDelta: back.duration - 1 / 3, comment: back.comment,
                 params: params, paramTypes: types, numKeys: mk.numKeys, props: T.reflectNames(back, "properties") };
    });

    section("expressionAccess", function () {
        var l = comp.layers.addText("x");
        var mk = l.property("ADBE Marker");
        var mv = new MarkerValue("AB");
        mv.duration = 0.5;
        mv.setParameters({ kind: "kf", furi: "[[\"a\",1,0.5,\"\"]]" });
        mk.setValueAtTime(1, mv);
        var p = textDoc(l);
        var out = {};
        var exprs = {
            paramKind: "var m = thisLayer.marker.key(1); m.parameters.kind",
            paramJson: "JSON.parse(thisLayer.marker.key(1).parameters.furi)[0][1].toString()",
            bareMarker: "marker.key(1).comment + '/' + marker.key(1).duration",
            hasJson: "typeof JSON"
        };
        for (var name in exprs) {
            p.expression = exprs[name];
            var v;
            try { v = p.valueAtTime(0, false).text; } catch (e) { v = "<error " + e.toString() + ">"; }
            out[name] = { value: v, error: p.expressionError };
        }
        p.expression = "";
        return out;
    });

    section("amountExpressions", function () {
        var l = comp.layers.addText("ABCD");
        var mk = l.property("ADBE Marker");
        var a = new MarkerValue("AB"); a.duration = 1; mk.setValueAtTime(0, a);
        var b = new MarkerValue("CD"); b.duration = 1; mk.setValueAtTime(1, b);
        var spec = "var acc = 0, amt = 0;\nfor (var k = 1; k <= marker.numKeys; k++) {\n  var m = marker.key(k), n = m.comment.length;\n  if (textIndex <= acc + n) {\n    var s = m.time + m.duration * (textIndex - acc - 1) / n;\n    amt = linear(time, s, s + m.duration / n, 0, 100);\n    break;\n  }\n  acc += n;\n}\namt;";
        var amount = addAnimator(l, [1, 0, 0], spec);
        var out = { valueType: amount.propertyValueType, value: amount.value };
        try { out.valueAt = amount.valueAtTime(0.75, false); } catch (e) { out.valueAt = "<error " + e.toString() + ">"; }
        out.error = amount.expressionError;
        out.enabled = amount.expressionEnabled;
        return out;
    });

    section("fonts", function () {
        var out = { exists: typeof app.fonts };
        if (!app.fonts) { return out; }
        out.methods = T.reflectNames(app.fonts, "methods");
        out.props = T.reflectNames(app.fonts, "properties");
        function desc(f) {
            if (!f) { return null; }
            var d = {};
            var ks = ["postScriptName", "familyName", "nativeFamilyName", "styleName", "nativeStyleName", "fullName",
                      "nativeFullName", "location", "isSubstitute", "fontID", "type", "technology", "hasDesignAxes"];
            for (var i = 0; i < ks.length; i++) { try { d[ks[i]] = f[ks[i]]; } catch (e) { d[ks[i]] = "<error>"; } }
            return d;
        }
        var arial = app.fonts.getFontsByPostScriptName("ArialMT");
        out.arialByPS = arial && arial.length ? desc(arial[0]) : null;
        out.fontObjectProps = arial && arial.length ? T.reflectNames(arial[0], "properties") : null;
        var ab = app.fonts.getFontsByFamilyNameAndStyleName("Arial", "Bold");
        out.arialBold = ab && ab.length ? desc(ab[0]) : null;
        out.missingPS = app.fonts.getFontsByPostScriptName("No-Such-Font-PS");
        out.byPS = {};
        var ps = ["GenJyuuGothic-Bold", "RyuminPr5-ExHeavy", "NotoSansJP-ExtraBold", "NotoSansJP-Black", "MicrosoftJhengHeiRegular"];
        for (var i = 0; i < ps.length; i++) {
            var r = app.fonts.getFontsByPostScriptName(ps[i]);
            out.byPS[ps[i]] = r && r.length ? desc(r[0]) : null;
        }
        out.byFamily = {};
        var fam = [["Gen Jyuu Gothic Bold", "Regular"], ["Gen Jyuu Gothic Bold", "Bold"], ["Gen Jyuu Gothic", "Bold"],
                   ["源柔ゴシック", "Bold"], ["A-OTF Ryumin Pr5", "EH-KL"],
                   ["A-OTF Ryumin Pr5 EH-KL", "Regular"], ["Noto Sans JP", "ExtraBold"], ["Noto Sans JP ExtraBold", "Regular"]];
        for (var j = 0; j < fam.length; j++) {
            var rr;
            try { rr = app.fonts.getFontsByFamilyNameAndStyleName(fam[j][0], fam[j][1]); } catch (e) { rr = "<error " + e.toString() + ">"; }
            out.byFamily[fam[j][0] + " / " + fam[j][1]] = rr && rr.length ? desc(rr[0]) : rr;
        }
        out.scan = [];
        var groups = app.fonts.allFonts;
        out.groupCount = groups.length;
        for (var g = 0; g < groups.length; g++) {
            for (var n = 0; n < groups[g].length; n++) {
                var f = groups[g][n];
                var key = (f.familyName + " " + f.nativeFamilyName + " " + f.fullName).toLowerCase();
                if (/gen jyuu|ryumin|noto sans jp|noto serif cjk|源柔/.test(key)) { out.scan.push(desc(f)); }
            }
        }
        return out;
    });

    section("inOut", function () {
        var l = comp.layers.addText("x");
        l.startTime = 0;
        var out = {};
        try { l.outPoint = 12; out.outPastComp = l.outPoint; } catch (e) { out.outPastComp = "<error " + e.toString() + ">"; }
        l.inPoint = 1.2345;
        out.inPointOffFrame = l.inPoint;
        out.frame = l.inPoint * 24000 / 1001;
        l.inPoint = 24 * 1001 / 24000;
        out.inPointOnFrame = l.inPoint;
        out.equalsExact = l.inPoint === 24 * 1001 / 24000;
        return out;
    });

    section("duplicate", function () {
        var t = comp.layers.addText("template");
        t.name = "KARA_TEMPLATE";
        t.comment = "user comment";
        t.enabled = false;
        t.inPoint = 2;
        var mv = new MarkerValue("m");
        t.property("ADBE Marker").setValueAtTime(3, mv);
        var d = t.duplicate();
        return { name: d.name, comment: d.comment, enabled: d.enabled, markers: d.property("ADBE Marker").numKeys,
                 inPoint: d.inPoint, startTime: d.startTime, index: d.index, templateIndex: t.index };
    });

    section("fontFile", function () {
        var r = app.fonts ? app.fonts.getFontsByPostScriptName("ArialMT") : null;
        if (!r || !r.length) { return null; }
        var f = new File(r[0].location);
        f.encoding = "BINARY";
        f.open("r");
        var head = f.read(12);
        f.close();
        return { path: r[0].location, exists: f.exists, firstBytes: T.codes(head) };
    });

    // Render one frame to see how textIndex counts line breaks, astral and combining characters.
    section("render", function () {
        var c = newComp("ass2ae_probe_textindex", 2);
        var tests = [
            ["AB\rCD", "textIndex == 3 ? 100 : 0", 150],                // red C => \r not counted
            ["AB\rCD", "textTotal == 5 ? 100 : 0", 420],                // all red => \r counted
            ["A😀BC", "textIndex == 3 ? 100 : 0", 690],       // red B => emoji is 1
            ["がKL", "textIndex == 2 ? 100 : 0", 960]          // red K => combining mark merged
        ];
        for (var i = 0; i < tests.length; i++) {
            var l = bigText(c, tests[i][0], tests[i][2]);
            addAnimator(l, [1, 0, 0], tests[i][1]);
        }
        // spec Amount expression at t=0.75: "AB" 0-1s, "CD" 1-2s => A 100%, B 50%, C/D 0%
        var s = bigText(c, "ABCD", 1050);
        s.property("ADBE Transform Group").property("ADBE Position").setValue([1200, 150]);
        var mk = s.property("ADBE Marker");
        var a = new MarkerValue("AB"); a.duration = 1; mk.setValueAtTime(0, a);
        var b = new MarkerValue("CD"); b.duration = 1; mk.setValueAtTime(1, b);
        var spec = "var acc = 0, amt = 0;\nfor (var k = 1; k <= marker.numKeys; k++) {\n  var m = marker.key(k), n = m.comment.length;\n  if (textIndex <= acc + n) {\n    var s = m.time + m.duration * (textIndex - acc - 1) / n;\n    amt = linear(time, s, s + m.duration / n, 0, 100);\n    break;\n  }\n  acc += n;\n}\namt;";
        var amount = addAnimator(s, [1, 0, 0], spec);
        var png = new File(outDir + "/probe_textindex.png");
        if (png.exists) { png.remove(); }
        c.saveFrameToPng(0.75, png);  // written after the script returns
        keepComps.push(c);
        return { png: png.fsName, specError: amount.expressionError };
    });

    for (var m = made.length - 1; m >= 0; m--) {
        var keep = false;
        for (var kc = 0; kc < keepComps.length; kc++) { if (keepComps[kc] === made[m]) { keep = true; } }
        if (!keep) { try { made[m].remove(); } catch (e) {} }
    }
    T.writeText(outDir + "/probe_api.json", T.toJson(R));
    T.writeText(outDir + "/probe_api.done", "ok");
})();
