// Runs generated ass2ae JSX files inside After Effects and dumps what they built.
// Driven by tools/ae/run_in_ae.py (config in $.global.ASS2AE_HARNESS). ES3.
(function () {
    var H = $.global.ASS2AE_HARNESS;
    var outDir = H.outDir;
    $.evalFile(File(outDir).parent.fsName + "/lib.jsx");
    var T = AETEST;
    var PREFIX = "ass2ae_test_";

    function textDoc(layer) { return layer.property("ADBE Text Properties").property("ADBE Text Document"); }
    function startsWith(s, p) { return typeof s === "string" && s.substr(0, p.length) === p; }

    // remove comps left over from earlier harness runs
    for (var i = app.project.numItems; i >= 1; i--) {
        var it = app.project.item(i);
        if (it instanceof CompItem && startsWith(it.name, PREFIX)) { it.remove(); }
    }

    function addTemplate(comp, name, font, fill) {
        var t = comp.layers.addText("TEMPLATE");
        t.name = name;
        var p = textDoc(t), td = p.value;
        td.resetCharStyle();
        td.font = font;
        td.fontSize = 72;
        td.applyFill = true;
        td.fillColor = fill;
        td.applyStroke = true;
        td.strokeColor = [0, 0, 0.3];
        td.strokeWidth = 6;
        td.strokeOverFill = false;
        td.justification = ParagraphJustification.LEFT_JUSTIFY;
        p.setValue(td);
        t.enabled = false;
        return t;
    }

    // a generic template plus a per-style one (KARA_TEMPLATE_K1) and an unrelated user layer
    function templateComp(name) {
        var comp = app.project.items.addComp(PREFIX + name, 1920, 1080, 1, 240, 24000 / 1001);
        var bg = comp.layers.addSolid([0.15, 0.15, 0.2], "USER_BG", 1920, 1080, 1);
        addTemplate(comp, "KARA_TEMPLATE", "NotoSansJP-Bold", [0.6, 0.8, 1]);
        addTemplate(comp, "KARA_TEMPLATE_K1", "GenJyuuGothic-Bold", [1, 0.9, 0.5]);
        bg.moveToEnd();
        return comp;
    }

    function dumpLayer(l) {
        var o = { index: l.index, name: l.name, comment: l.comment, enabled: l.enabled, inPoint: l.inPoint,
                  outPoint: l.outPoint, startTime: l.startTime, generated: startsWith(l.comment, "[ass2ae]") };
        if (!(l instanceof TextLayer)) { return o; }
        var td = textDoc(l).value;
        o.text = td.text;
        o.font = td.font;
        o.fontSize = td.fontSize;
        o.fillColor = td.fillColor;
        o.justification = String(td.justification);
        try { o.baselineLocs = td.baselineLocs; } catch (e) {}
        var tr = l.property("ADBE Transform Group");
        o.anchor = tr.property("ADBE Anchor Point").value;
        o.position = tr.property("ADBE Position").value;
        o.rect = l.sourceRectAtTime(l.inPoint, false);
        o.markers = [];
        var mk = l.property("ADBE Marker");
        for (var k = 1; k <= mk.numKeys; k++) {
            var v = mk.keyValue(k);
            var params = null;
            try { params = v.getParameters(); } catch (e2) { params = "<error " + e2.toString() + ">"; }
            o.markers.push({ t: mk.keyTime(k), d: v.duration, c: v.comment, params: params });
        }
        var anims = l.property("ADBE Text Properties").property("ADBE Text Animators");
        for (var a = 1; a <= anims.numProperties; a++) {
            var an = anims.property(a);
            if (an.name !== "ass2ae karaoke") { continue; }
            o.selectors = [];
            var sels = an.property("ADBE Text Selectors");
            for (var s = 1; s <= sels.numProperties; s++) { o.selectors.push(sels.property(s).matchName); }
            var sel = sels.property("ADBE Text Expressible Selector");
            if (sel) {
                o.basedOn = sel.property("ADBE Text Range Type2").value;
                o.amountError = sel.property("ADBE Text Expressible Amount").expressionError;
            }
            o.sung = an.property("ADBE Text Animator Properties").property("ADBE Text Fill Color").value;
        }
        return o;
    }

    for (var c = 0; c < H.cases.length; c++) {
        var cs = H.cases[c];
        var res = { name: cs.name, runs: [], mustSurvive: [] };
        var comp = null;
        try {
            if (cs.mode === "template") {
                comp = templateComp(cs.name);
                res.mustSurvive = ["KARA_TEMPLATE", "KARA_TEMPLATE_K1", "USER_BG"];
            }
            for (var r = 0; r < cs.runs; r++) {
                $.global.ASS2AE_HEADLESS = true;
                $.global.ASS2AE_RESULT = null;
                $.global.ASS2AE_TARGET = comp ? comp : "new";
                try {
                    $.evalFile(cs.jsx);
                    res.runs.push({ result: $.global.ASS2AE_RESULT });
                } catch (e) {
                    res.runs.push({ error: e.toString() + " line " + e.line });
                }
                if (!comp && $.global.ASS2AE_RESULT && $.global.ASS2AE_RESULT.summary) {
                    comp = app.project.itemByID($.global.ASS2AE_RESULT.summary.compId);
                }
            }
            res.frames = [];
            for (var f = 0; f < cs.renderTimes.length; f++) {
                var png = new File(outDir + "/" + cs.name + "_" + f + ".png");
                if (png.exists) { png.remove(); }
                // written asynchronously after the script returns; run_in_ae.py waits for it
                comp.saveFrameToPng(cs.renderTimes[f], png);
                res.frames.push({ time: cs.renderTimes[f], file: png.fsName });
            }
            res.comp = { name: comp.name, frameRate: comp.frameRate, width: comp.width, height: comp.height };
            res.layers = [];
            for (var li = 1; li <= comp.numLayers; li++) { res.layers.push(dumpLayer(comp.layer(li))); }
        } catch (err) {
            res.error = err.toString() + " line " + err.line;
        }
        T.writeText(outDir + "/" + cs.name + ".result.json", T.toJson(res));
    }
    // let AE render the requested frames (it does so while the script sleeps)
    for (var w = 0; w < H.cases.length; w++) {
        for (var wf = 0; wf < H.cases[w].renderTimes.length; wf++) {
            T.waitForFile(outDir + "/" + H.cases[w].name + "_" + wf + ".png", 60);
        }
    }
    $.global.ASS2AE_HEADLESS = false;
    $.global.ASS2AE_TARGET = null;
    T.writeText(outDir + "/harness.done", "ok");
})();
