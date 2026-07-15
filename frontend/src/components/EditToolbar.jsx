import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { DoorOpen, Square, PenSquare, Trash2, Save, X } from "lucide-react";
import { Button } from "./ui/button";
import { ANALYSIS } from "../constants/testIds";

/**
 * Floating edit-mode toolbar (Linear-style).
 * Props:
 *  visible     boolean
 *  onAdd(type) — type of object to add: 'wall_internal' | 'door' | 'window'
 *  onDelete()  — delete selected object
 *  onSave()    — persist edits
 *  onExit()    — exit edit mode
 *  hasSelection boolean
 *  saving      boolean
 */
const EditToolbar = ({ visible, onAdd, onDelete, onSave, onExit, hasSelection, saving }) => {
  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 16 }}
          transition={{ duration: 0.18, ease: "easeOut" }}
          className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 glass border border-border rounded-full pl-2 pr-2 py-1.5 shadow-lg flex items-center gap-1"
        >
          <span className="overline pl-2 pr-1">Edit</span>
          <div className="w-px h-6 bg-border mx-1" />
          <ToolBtn
            testid={ANALYSIS.toolAddWall}
            onClick={() => onAdd("wall_internal")}
            icon={PenSquare}
            label="Add wall"
          />
          <ToolBtn
            testid={ANALYSIS.toolAddDoor}
            onClick={() => onAdd("door")}
            icon={DoorOpen}
            label="Add door"
          />
          <ToolBtn
            testid={ANALYSIS.toolAddWindow}
            onClick={() => onAdd("window")}
            icon={Square}
            label="Add window"
          />
          <div className="w-px h-6 bg-border mx-1" />
          <ToolBtn
            testid={ANALYSIS.toolDelete}
            onClick={onDelete}
            icon={Trash2}
            label="Delete selected"
            disabled={!hasSelection}
            danger
          />
          <div className="w-px h-6 bg-border mx-1" />
          <Button
            data-testid={ANALYSIS.saveEditsBtn}
            onClick={onSave}
            disabled={saving}
            size="sm"
            className="rounded-full h-8 gap-1.5"
          >
            <Save className="w-3.5 h-3.5" />
            {saving ? "Saving…" : "Save"}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={onExit}
            className="rounded-full w-8 h-8"
            aria-label="Exit edit mode"
          >
            <X className="w-3.5 h-3.5" />
          </Button>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

const ToolBtn = ({ icon: Icon, label, onClick, disabled, danger, testid }) => (
  <button
    data-testid={testid}
    onClick={onClick}
    disabled={disabled}
    title={label}
    className={`h-8 px-2.5 rounded-full text-xs inline-flex items-center gap-1.5 transition-colors ${
      disabled
        ? "text-muted-foreground opacity-40 cursor-not-allowed"
        : danger
        ? "text-destructive hover:bg-destructive/10"
        : "hover:bg-secondary"
    }`}
  >
    <Icon className="w-3.5 h-3.5" />
    <span className="hidden md:inline">{label}</span>
  </button>
);

export default EditToolbar;
