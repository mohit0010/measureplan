import React from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowRight,
  Ruler,
  ScanLine,
  Eye,
  Layers,
  FileDown,
  Sparkles,
} from "lucide-react";
import Nav from "../components/Navbar";
import UploadDropzone from "../components/UploadDropzone";
import { Button } from "../components/ui/button";
import { HOME } from "../constants/testIds";

const features = [
  {
    icon: ScanLine,
    title: "Vision-native detection",
    desc: "Reads walls, doors, windows, dimensions and room labels straight from the drawing.",
  },
  {
    icon: Ruler,
    title: "Feet & meters",
    desc: "Auto-derived from annotated dimensions or standard proportions with a confidence score.",
  },
  {
    icon: Eye,
    title: "Interactive plan viewer",
    desc: "Zoom, pan and hover to inspect every detected object with per-item confidence.",
  },
  {
    icon: Layers,
    title: "Manual correction",
    desc: "Add, delete or relabel walls, doors, windows and rooms — counts update instantly.",
  },
  {
    icon: FileDown,
    title: "One-click PDF report",
    desc: "Studio-grade PDF with preview, summary metrics and per-room breakdown.",
  },
  {
    icon: Sparkles,
    title: "Modular by design",
    desc: "Same building data flows into future modules: BOQ, brick, paint and cost calculators.",
  },
];

const Home = () => {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <Nav />

      {/* HERO */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bp-grid opacity-40 pointer-events-none" />
        <div className="absolute -top-40 -right-20 w-[520px] h-[520px] rounded-full bg-primary/10 blur-3xl pointer-events-none" />

        <div className="relative max-w-[1440px] mx-auto px-6 pt-20 pb-24 lg:pt-28 lg:pb-32">
          <div className="grid lg:grid-cols-12 gap-10 items-start">
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, ease: "easeOut" }}
              className="lg:col-span-7"
            >
              <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-[11px] font-mono-plex text-muted-foreground">
                <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
                PlanMeasure AI · v1.0 · Vision Model Online
              </div>
              <h1 className="mt-6 font-display font-bold text-4xl sm:text-5xl lg:text-6xl leading-[1.02] tracking-tight">
                Turn any floor plan into
                <br className="hidden sm:block" /> a{" "}
                <span className="text-primary">structured building brief</span>{" "}
                in seconds.
              </h1>
              <p className="mt-6 text-base md:text-lg text-muted-foreground max-w-xl leading-relaxed">
                Drop a PDF, PNG or JPG and PlanMeasure AI extracts wall lengths,
                room counts, doors, windows and confidence — ready to power
                estimates, BOQs and cost sheets.
              </p>

              <div className="mt-8 flex flex-wrap items-center gap-3">
                <a href="#upload">
                  <Button
                    data-testid={HOME.heroCtaUpload}
                    size="lg"
                    className="rounded-full px-6 h-11 gap-2"
                  >
                    Upload a plan
                    <ArrowRight className="w-4 h-4" />
                  </Button>
                </a>
                <Link to="/history">
                  <Button
                    data-testid={HOME.heroCtaDemo}
                    size="lg"
                    variant="outline"
                    className="rounded-full h-11"
                  >
                    View history
                  </Button>
                </Link>
              </div>

              <div className="mt-10 grid grid-cols-3 max-w-md gap-6">
                <MetricStub label="Formats" value="PDF · PNG · JPG" />
                <MetricStub label="Metrics" value="9+" />
                <MetricStub label="Modular" value="BOQ-ready" />
              </div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.55, ease: "easeOut", delay: 0.1 }}
              className="lg:col-span-5"
              id="upload"
            >
              <UploadDropzone />
              <div className="mt-3 text-[11px] text-muted-foreground font-mono-plex">
                No login required · Files processed in-memory · Vision by Gemini 3
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* MOCK RESULT PREVIEW */}
      <section className="relative border-t border-border">
        <div className="max-w-[1440px] mx-auto px-6 py-20">
          <div className="grid lg:grid-cols-12 gap-8 items-start">
            <div className="lg:col-span-4">
              <div className="overline">Live preview</div>
              <h2 className="font-display font-bold text-3xl lg:text-4xl mt-3 tracking-tight leading-[1.05]">
                Every metric an estimator needs — on one page.
              </h2>
              <p className="mt-4 text-muted-foreground leading-relaxed">
                Instead of tracing walls by hand, get a technical summary with
                confidence scoring, unit conversion and object-level details
                you can trust.
              </p>
            </div>
            <div className="lg:col-span-8">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <FakeStat label="Total wall length" value="356.4" unit="ft" />
                <FakeStat label="External walls" value="154.2" unit="ft" />
                <FakeStat label="Internal walls" value="202.2" unit="ft" />
                <FakeStat label="Rooms" value="7" />
                <FakeStat label="Bathrooms" value="3" />
                <FakeStat label="Doors" value="15" />
                <FakeStat label="Windows" value="18" />
                <FakeStat label="Built-up area" value="1,240" unit="ft²" />
                <FakeStat
                  label="AI confidence"
                  value="96"
                  unit="%"
                  accent
                />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* FEATURES */}
      <section className="relative border-t border-border">
        <div className="max-w-[1440px] mx-auto px-6 py-24">
          <div className="max-w-2xl">
            <div className="overline">Capabilities</div>
            <h2 className="font-display font-bold text-3xl lg:text-4xl mt-3 tracking-tight leading-[1.05]">
              Built like a CAD tool. Feels like Linear.
            </h2>
          </div>

          <div className="mt-12 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 border-t border-l border-border">
            {features.map((f) => (
              <div
                key={f.title}
                className="p-6 border-r border-b border-border relative group hover:bg-secondary/40 transition-colors"
              >
                <div className="w-10 h-10 rounded-md bg-primary/10 text-primary grid place-items-center">
                  <f.icon className="w-5 h-5" strokeWidth={2} />
                </div>
                <div className="mt-4 font-display font-bold text-lg">
                  {f.title}
                </div>
                <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
                  {f.desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <footer className="border-t border-border">
        <div className="max-w-[1440px] mx-auto px-6 py-8 flex flex-col md:flex-row justify-between gap-4 items-start md:items-center">
          <div className="text-xs text-muted-foreground font-mono-plex">
            © 2026 PlanMeasure AI · Floor Plan Intelligence
          </div>
          <div className="text-xs text-muted-foreground font-mono-plex">
            Approximate measurements only. Verify on site before construction.
          </div>
        </div>
      </footer>
    </div>
  );
};

const MetricStub = ({ label, value }) => (
  <div>
    <div className="overline">{label}</div>
    <div className="mt-1 font-mono-plex text-sm text-foreground">{value}</div>
  </div>
);

const FakeStat = ({ label, value, unit, accent }) => (
  <div
    className={`rounded-md border border-border bg-card p-4 ${
      accent ? "ring-1 ring-primary/40" : ""
    }`}
  >
    <div className="overline text-[10px]">{label}</div>
    <div className="mt-2 flex items-baseline gap-1.5">
      <span className={`stat-num text-2xl ${accent ? "text-primary" : ""}`}>
        {value}
      </span>
      {unit && (
        <span className="text-xs text-muted-foreground font-mono-plex">
          {unit}
        </span>
      )}
    </div>
  </div>
);

export default Home;
