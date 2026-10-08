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
    function templateComp(name, duration) {
        var comp = app.project.items.addComp(PREFIX + name, 1920, 1080, 1, Math.max(240, duration), 24000 / 1001);
        var bg = comp.layers.addSolid([0.15, 0.15, 0.2], "USER_BG", 1920, 1080, 1);
        addTemplate(comp, "KARA_TEMPLATE", "NotoSansJP-Bold", [0.6, 0.8, 1]);
        addTemplate(comp, "KARA_TEMPLATE_K1", "GenJyuuGothic-Bold", [1, 0.9, 0.5]);
        bg.moveToEnd();
        return comp;
    }

    // Anchor point and text box corners in comp space, evaluated by a temporary expression.
    function compGeometry(l) {
        var fx = l.property("ADBE Effect Parade").addProperty("ADBE Point Control");
        var pt = fx.property(1);
        var out = {};
        var exprs = {
            anchor: "toComp(transform.anchorPoint)",
            topLeft: "var r = sourceRectAtTime(time, false); toComp([r.left, r.top])",
            bottomRight: "var r = sourceRectAtTime(time, false); toComp([r.left + r.width, r.top + r.height])"
        };
        for (var k in exprs) {
            pt.expression = exprs[k];
            out[k] = pt.valueAtTime(l.inPoint, false);
        }
        fx.remove();
        return out;
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
        o.parent = l.parent ? l.parent.name : null;
        o.comp = compGeometry(l);
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
                comp = templateComp(cs.name, cs.duration);
                res.mustSurvive = ["KARA_TEMPLATE", "KARA_TEMPLATE_K1", "USER_BG"];
            }
            for (var r = 0; r < cs.runs; r++) {
                $.global.ASS2AE_HEADLESS = true;
                $.global.ASS2AE_RESULT = null;
                // The first run names its target (as the project builder does); later runs use
                // the comp open in the viewer, like a user running the script on the active comp.
                var viaViewer = r > 0 && comp;
                if (viaViewer) {
                    comp.openInViewer();
                    $.global.ASS2AE_TARGET = null;
                } else {
                    $.global.ASS2AE_TARGET = comp ? comp : "new";
                }
                var t0 = new Date().getTime();
                var run = { viaViewer: !!viaViewer };
                try {
                    $.evalFile(cs.jsx);
                    run.result = $.global.ASS2AE_RESULT;
                } catch (e) {
                    run.error = e.toString() + " line " + e.line;
                }
                run.seconds = (new Date().getTime() - t0) / 1000;
                var active = app.project.activeItem;
                run.activeAfter = active ? active.name : null;
                res.runs.push(run);
                if (!comp && $.global.ASS2AE_RESULT && $.global.ASS2AE_RESULT.summary) {
                    comp = app.project.itemByID($.global.ASS2AE_RESULT.summary.compId);
                }
            }
            res.leftovers = [];
            for (var it2 = 1; it2 <= app.project.numItems; it2++) {
                if (app.project.item(it2).name === "_ass2ae_redirect_") { res.leftovers.push(it2); }
            }
            res.frames = [];
            for (var f = 0; f < cs.renderTimes.length; f++) {
                res.frames.push(T.renderFrame(comp, cs.renderTimes[f], outDir + "/" + cs.name + "_" + f));
            }
            res.comp = { name: comp.name, frameRate: comp.frameRate, width: comp.width, height: comp.height };
            res.layers = [];
            for (var li = 1; li <= comp.numLayers; li++) { res.layers.push(dumpLayer(comp.layer(li))); }
        } catch (err) {
            res.error = err.toString() + " line " + err.line;
        }
        T.writeText(outDir + "/" + cs.name + ".result.json", T.toJson(res));
    }
    $.global.ASS2AE_HEADLESS = false;
    $.global.ASS2AE_TARGET = null;
    T.writeText(outDir + "/harness.done", "ok");
})();
