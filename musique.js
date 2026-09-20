/*
 * Deux musiques de fond synthétisées dans le navigateur (Web Audio API).
 * Aucun fichier audio : rien à télécharger, rien à licencier.
 *
 *   Musique.jouer("calme" | "rythmee")   lance une piste (arrête l'autre)
 *   Musique.basculer(nom)                lance la piste, ou l'arrête si elle joue déjà
 *   Musique.arreter()                    coupe la musique
 *   Musique.courante()                   "calme", "rythmee" ou null
 *   Musique.surChangement(fn)            fn(nomCourant) à chaque changement
 *   Musique.disponible                   false si le navigateur n'a pas Web Audio
 */
(function () {
  "use strict";

  var AC = window.AudioContext || window.webkitAudioContext;
  var ctx = null;          // contexte audio (créé au premier toucher, exigé par iOS)
  var sortie = null;       // bus maître
  var bruit = null;        // tampon de bruit blanc (percussions)
  var reverbBuf = null;    // réponse impulsionnelle de la réverbération
  var actuelle = null;     // { nom, piste }
  var ecouteurs = [];

  // La mineur – Fa – Do – Sol : une boucle harmonique simple et agréable
  var ACCORDS = [
    { racine: 45, notes: [57, 60, 64] },
    { racine: 41, notes: [57, 60, 65] },
    { racine: 48, notes: [55, 60, 64] },
    { racine: 43, notes: [55, 59, 62] }
  ];
  var PENTATONIQUE = [69, 72, 74, 76, 79, 81, 84];   // La mineur pentatonique

  function hz(midi) { return 440 * Math.pow(2, (midi - 69) / 12); }

  // ------------------------------------------------------------------ init
  function init() {
    if (ctx) return;
    // iOS : joue le son même quand l'interrupteur « silencieux » est activé
    if (navigator.audioSession) { try { navigator.audioSession.type = "playback"; } catch (e) {} }

    ctx = new AC();
    var compresseur = ctx.createDynamicsCompressor();
    sortie = ctx.createGain();
    sortie.gain.value = 0.8;
    sortie.connect(compresseur);
    compresseur.connect(ctx.destination);

    bruit = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate);
    var d = bruit.getChannelData(0);
    for (var i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;

    var longueur = Math.floor(ctx.sampleRate * 2.6);
    reverbBuf = ctx.createBuffer(2, longueur, ctx.sampleRate);
    for (var c = 0; c < 2; c++) {
      var r = reverbBuf.getChannelData(c);
      for (var j = 0; j < longueur; j++) r[j] = (Math.random() * 2 - 1) * Math.pow(1 - j / longueur, 2.5);
    }

    // Certains navigateurs mettent le son en pause (appel, retour sur l'onglet) : on le relance
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden && actuelle && ctx.state !== "running") ctx.resume();
    });
  }

  // ------------------------------------------------- bus d'une piste (fx)
  function creerBus(o) {
    var maintenant = ctx.currentTime;
    var entree = ctx.createGain();
    var fondu = ctx.createGain();
    fondu.gain.setValueAtTime(0, maintenant);
    fondu.gain.linearRampToValueAtTime(1, maintenant + 1.2);
    entree.connect(fondu);

    // réverbération
    var conv = ctx.createConvolver();
    conv.buffer = reverbBuf;
    var envoiRev = ctx.createGain();
    envoiRev.gain.value = o.rev;
    entree.connect(envoiRev); envoiRev.connect(conv); conv.connect(fondu);

    // écho avec rebouclage adouci
    var retard = ctx.createDelay(1.0);
    retard.delayTime.value = o.delai;
    var fb = ctx.createGain(); fb.gain.value = 0.35;
    var filtre = ctx.createBiquadFilter(); filtre.type = "lowpass"; filtre.frequency.value = 2400;
    var envoiEcho = ctx.createGain(); envoiEcho.gain.value = o.echo;
    entree.connect(envoiEcho); envoiEcho.connect(retard);
    retard.connect(filtre); filtre.connect(fb); fb.connect(retard);
    filtre.connect(fondu);

    fondu.connect(sortie);

    return {
      entree: entree,
      fin: function (voix) {
        var t = ctx.currentTime;
        fondu.gain.cancelScheduledValues(t);
        fondu.gain.setValueAtTime(fondu.gain.value, t);
        fondu.gain.linearRampToValueAtTime(0, t + 0.5);
        setTimeout(function () {
          voix.forEach(function (osc) { try { osc.stop(); } catch (e) {} });
          try { entree.disconnect(); } catch (e) {}
          try { fondu.disconnect(); } catch (e) {}
        }, 700);
      }
    };
  }

  // ---------------------------------------------------------- instruments
  function pad(bus, accord, t, dur, vol, attaque, relache, voix, avecBasse) {
    var g = ctx.createGain();
    var filtre = ctx.createBiquadFilter();
    filtre.type = "lowpass"; filtre.frequency.value = 1100;
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(vol, t + attaque);
    g.gain.setValueAtTime(vol, t + Math.max(attaque, dur));
    g.gain.linearRampToValueAtTime(0, t + dur + relache);
    g.connect(filtre); filtre.connect(bus.entree);

    var notes = accord.notes.slice();
    var oscs = [];
    notes.forEach(function (m) {
      [-6, 6].forEach(function (cents) { oscs.push({ f: hz(m), type: "triangle", det: cents }); });
    });
    if (avecBasse) oscs.push({ f: hz(accord.racine), type: "sine", det: 0 });

    oscs.forEach(function (p) {
      var osc = ctx.createOscillator();
      osc.type = p.type; osc.frequency.value = p.f; osc.detune.value = p.det;
      osc.connect(g);
      osc.start(t); osc.stop(t + dur + relache + 0.1);
      voix.push(osc);
    });
  }

  function cloche(bus, midi, t) {
    [[1, 0.06], [2.01, 0.02]].forEach(function (h) {
      var osc = ctx.createOscillator();
      var g = ctx.createGain();
      osc.type = "sine"; osc.frequency.value = hz(midi) * h[0];
      g.gain.setValueAtTime(0.0001, t);
      g.gain.linearRampToValueAtTime(h[1], t + 0.01);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 3.2);
      osc.connect(g); g.connect(bus.entree);
      osc.start(t); osc.stop(t + 3.3);
    });
  }

  function grosseCaisse(bus, t) {
    var osc = ctx.createOscillator();
    var g = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(140, t);
    osc.frequency.exponentialRampToValueAtTime(42, t + 0.13);
    g.gain.setValueAtTime(0.9, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + 0.4);
    osc.connect(g); g.connect(bus.entree);
    osc.start(t); osc.stop(t + 0.42);
  }

  function souffle(bus, t, dur, type, freq, q, vol) {
    var src = ctx.createBufferSource();
    src.buffer = bruit;
    var f = ctx.createBiquadFilter();
    f.type = type; f.frequency.value = freq; f.Q.value = q;
    var g = ctx.createGain();
    g.gain.setValueAtTime(vol, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + dur);
    src.connect(f); f.connect(g); g.connect(bus.entree);
    src.start(t, Math.random() * 1.5, dur + 0.02);
  }

  function charleston(bus, t, vol) { souffle(bus, t, 0.05, "highpass", 7000, 0.7, vol); }
  function clap(bus, t) { souffle(bus, t, 0.16, "bandpass", 1600, 0.9, 0.35); }

  function basse(bus, midi, t, dur) {
    var osc = ctx.createOscillator();
    var f = ctx.createBiquadFilter();
    var g = ctx.createGain();
    osc.type = "sawtooth"; osc.frequency.value = hz(midi);
    f.type = "lowpass"; f.frequency.value = 380; f.Q.value = 2;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(0.2, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.001, t + dur);
    osc.connect(f); f.connect(g); g.connect(bus.entree);
    osc.start(t); osc.stop(t + dur + 0.05);
  }

  function pincee(bus, midi, t, vol) {
    var osc = ctx.createOscillator();
    var f = ctx.createBiquadFilter();
    var g = ctx.createGain();
    osc.type = "triangle"; osc.frequency.value = hz(midi);
    f.type = "lowpass";
    f.frequency.setValueAtTime(3200, t);
    f.frequency.exponentialRampToValueAtTime(500, t + 0.25);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(vol, t + 0.005);
    g.gain.exponentialRampToValueAtTime(0.001, t + 0.3);
    osc.connect(f); f.connect(g); g.connect(bus.entree);
    osc.start(t); osc.stop(t + 0.32);
  }

  // --------------------------------------------------------------- pistes
  // Piste 1 : nappes lentes et petites cloches aléatoires, sur 4 accords de 8 s
  function pisteCalme() {
    var bus = creerBus({ rev: 0.5, echo: 0.3, delai: 0.5 });
    var voix = [];
    var t = ctx.currentTime + 0.15;
    var i = 0;

    function planifier() {
      while (t < ctx.currentTime + 2.5) {
        pad(bus, ACCORDS[i % 4], t, 8, 0.05, 2.5, 2.5, voix, true);
        var bt = t + 0.8 + Math.random();
        while (bt < t + 8) {
          cloche(bus, PENTATONIQUE[Math.floor(Math.random() * PENTATONIQUE.length)], bt);
          bt += 1.4 + Math.random() * 2.4;
        }
        t += 8; i++;
      }
    }
    planifier();
    var minuteur = setInterval(planifier, 500);
    return { arreter: function () { clearInterval(minuteur); bus.fin(voix); } };
  }

  // Piste 2 : 100 BPM, grosse caisse, claps, basse et arpège
  function pisteRythmee() {
    var bpm = 100;
    var pas = 60 / bpm / 4;                              // une double-croche
    var bus = creerBus({ rev: 0.22, echo: 0.28, delai: 60 / bpm * 0.75 });
    var voix = [];
    var t = ctx.currentTime + 0.15;
    var n = 0;
    var ARPEGE = [0, 1, 2, 1, 0, 1, 2, 1];
    var BASSE = { 0: 0, 3: 0, 6: 12, 8: 0, 11: 0, 14: 12 };

    function planifier() {
      while (t < ctx.currentTime + 1.5) {
        var s = n % 16;
        var accord = ACCORDS[Math.floor(n / 16) % 4];
        if (s === 0) pad(bus, accord, t, pas * 16, 0.03, 0.15, 0.5, voix, false);
        if (s % 4 === 0) grosseCaisse(bus, t);
        if (s === 4 || s === 12) clap(bus, t);
        if (s % 4 === 2) charleston(bus, t, 0.10);
        else if (s % 2 === 1) charleston(bus, t, 0.03);
        if (BASSE.hasOwnProperty(s)) basse(bus, accord.racine + BASSE[s], t, pas * 2.2);
        if (s % 2 === 0) pincee(bus, accord.notes[ARPEGE[(s / 2) % 8]] + 12, t, s === 0 ? 0.11 : 0.075);
        t += pas; n++;
      }
    }
    planifier();
    var minuteur = setInterval(planifier, 200);
    return { arreter: function () { clearInterval(minuteur); bus.fin(voix); } };
  }

  // ------------------------------------------------------------------ API
  function notifier() {
    var nom = actuelle ? actuelle.nom : null;
    ecouteurs.forEach(function (fn) { fn(nom); });
  }

  function arreter() {
    if (actuelle) { actuelle.piste.arreter(); actuelle = null; }
    notifier();
  }

  function jouer(nom) {
    if (!AC) return;
    init();
    if (ctx.state !== "running") ctx.resume();
    if (actuelle) { actuelle.piste.arreter(); actuelle = null; }
    actuelle = { nom: nom, piste: nom === "calme" ? pisteCalme() : pisteRythmee() };
    notifier();
  }

  window.Musique = {
    disponible: !!AC,
    jouer: jouer,
    arreter: arreter,
    basculer: function (nom) { if (actuelle && actuelle.nom === nom) arreter(); else jouer(nom); },
    courante: function () { return actuelle ? actuelle.nom : null; },
    surChangement: function (fn) { ecouteurs.push(fn); }
  };
})();
