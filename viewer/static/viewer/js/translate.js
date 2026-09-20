/**
 * Pure translation between the Weave Viewer Payload contract and vis-network's
 * data/option shapes. This is the ONLY module that knows both shapes.
 *
 * Renderer-independence rule: only fields this file explicitly understands
 * are ever mapped into vis-network objects. `style.extra` / `viewer_config`
 * `extra` values are preserved on the payload but are never spread into the
 * translated output — they exist purely as a forward-compatible extension
 * point on the contract itself, not as a vis-network options passthrough.
 *
 * Omission rule: optional fields that are absent/null in the Weave payload
 * are simply left out of the translated object (never emitted as an
 * explicit "unset" placeholder). This is safe because WeaveViewer.update()
 * always removes a DataSet entry before adding its freshly translated
 * replacement, so an omitted key can never survive from a prior version.
 */

export class ViewerPayloadValidationError extends Error {}

function isPlainObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function assertValidPayload(payload) {
  if (!isPlainObject(payload)) {
    throw new ViewerPayloadValidationError("payload must be an object");
  }

  if (typeof payload.schema_version !== "string" || !payload.schema_version) {
    throw new ViewerPayloadValidationError("payload.schema_version is required");
  }

  if (!Array.isArray(payload.nodes)) {
    throw new ViewerPayloadValidationError("payload.nodes must be an array");
  }

  if (!Array.isArray(payload.edges)) {
    throw new ViewerPayloadValidationError("payload.edges must be an array");
  }

  const nodeIds = new Set();
  for (const node of payload.nodes) {
    if (!isPlainObject(node) || typeof node.id !== "string" || !node.id) {
      throw new ViewerPayloadValidationError("every node requires a non-empty string id");
    }
    if (nodeIds.has(node.id)) {
      throw new ViewerPayloadValidationError(`duplicate node id: ${node.id}`);
    }
    nodeIds.add(node.id);

    if (typeof node.type_key !== "string" || !node.type_key) {
      throw new ViewerPayloadValidationError(`node ${node.id} is missing type_key`);
    }
    if (typeof node.label !== "string") {
      throw new ViewerPayloadValidationError(`node ${node.id} is missing label`);
    }
  }

  const edgeIds = new Set();
  for (const edge of payload.edges) {
    if (!isPlainObject(edge) || typeof edge.id !== "string" || !edge.id) {
      throw new ViewerPayloadValidationError("every edge requires a non-empty string id");
    }
    if (edgeIds.has(edge.id)) {
      throw new ViewerPayloadValidationError(`duplicate edge id: ${edge.id}`);
    }
    edgeIds.add(edge.id);

    if (typeof edge.relationship_type_key !== "string" || !edge.relationship_type_key) {
      throw new ViewerPayloadValidationError(`edge ${edge.id} is missing relationship_type_key`);
    }
    if (!nodeIds.has(edge.source)) {
      throw new ViewerPayloadValidationError(`edge ${edge.id} source ${edge.source} does not reference an existing node`);
    }
    if (!nodeIds.has(edge.target)) {
      throw new ViewerPayloadValidationError(`edge ${edge.id} target ${edge.target} does not reference an existing node`);
    }
  }
}

function escapeLabelHtml(text) {
  return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/**
 * vis-network cannot bold a plain label, only markup inside a `multi` label.
 * So a Weave `font.weight: "bold"` becomes an html-multi font plus a <b>-wrapped,
 * escaped label; `weight` itself is never passed on to vis-network.
 */
function translateNodeFont(font, label) {
  const { weight, ...visFont } = font;
  if (weight !== "bold") {
    return { font: visFont, label };
  }
  return {
    font: { ...visFont, multi: "html" },
    label: `<b>${escapeLabelHtml(label)}</b>`,
  };
}

export function translateNode(node) {
  const style = node.style || {};
  const translated = {
    id: node.id,
    label: node.label,
    weaveData: {
      type_key: node.type_key,
      data: node.data || {},
    },
  };

  if (style.shape != null) translated.shape = style.shape;
  if (style.background != null || style.border != null) {
    translated.color = {};
    if (style.background != null) translated.color.background = style.background;
    if (style.border != null) translated.color.border = style.border;
    // vis-network recolours a selected/hovered node with its own blue by default,
    // which would override the item's semantic colours. Selection and hover keep
    // the item's colours; emphasis comes from border width and item states.
    const own = { ...translated.color };
    translated.color.highlight = { ...own };
    translated.color.hover = { ...own };
  }
  if (style.border_width != null) translated.borderWidth = style.border_width;
  if (style.font && Object.keys(style.font).length > 0) {
    const { font, label } = translateNodeFont(style.font, node.label);
    translated.label = label;
    if (Object.keys(font).length > 0) translated.font = font;
  }
  if (style.size != null) translated.size = style.size;
  if (style.image != null) translated.image = style.image;

  return translated;
}

export function translateEdge(edge) {
  const style = edge.style || {};
  const translated = {
    id: edge.id,
    from: edge.source,
    to: edge.target,
    weaveData: {
      relationship_type_key: edge.relationship_type_key,
      data: edge.data || {},
    },
  };

  if (edge.label != null) translated.label = edge.label;
  if (style.colour != null) translated.color = style.colour;
  if (style.width != null) translated.width = style.width;
  if (style.dashes != null) translated.dashes = style.dashes;
  if (style.arrows != null) translated.arrows = style.arrows;
  if (style.font && Object.keys(style.font).length > 0) translated.font = style.font;

  return translated;
}

// ----------------------------------------------------------------------------
// Interaction states
//
// A generic, renderer-facing vocabulary for "how does this item relate to what
// the user is looking at": selected, related (to the selection) or dimmed. The
// states never redefine an item's semantic colours or shape: they are derived
// from the item's own base translation (heavier border, lower opacity, faded
// label), so they are always reversible by re-deriving from that base.
//
// Both functions return the *complete* set of state-affected keys, including
// for the default state, because a DataSet.update() merges: a key that a state
// set earlier must be explicitly reset, not merely omitted.
// ----------------------------------------------------------------------------

export const ITEM_STATES = Object.freeze(["selected", "related", "dimmed"]);

const DIMMED_ITEM_OPACITY = 0.18;
const DIMMED_LABEL_ALPHA = 0.22;
const VIS_DEFAULT_BORDER_WIDTH = 1;
const VIS_DEFAULT_EDGE_WIDTH = 1;

/** "#RGB"/"#RRGGBB" -> "rgba(r,g,b,alpha)"; any other colour is returned unchanged. */
export function withAlpha(colour, alpha) {
  if (typeof colour !== "string") return colour;
  const match = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(colour.trim());
  if (!match) return colour;
  let hex = match[1];
  if (hex.length === 3) hex = hex.split("").map((c) => c + c).join("");
  const channel = (i) => parseInt(hex.slice(i, i + 2), 16);
  return `rgba(${channel(0)}, ${channel(2)}, ${channel(4)}, ${alpha})`;
}

function fadedFont(font) {
  return font && font.color ? { ...font, color: withAlpha(font.color, DIMMED_LABEL_ALPHA) } : font;
}

export function applyNodeState(base, state) {
  const borderWidth = base.borderWidth ?? VIS_DEFAULT_BORDER_WIDTH;
  const item = { ...base, opacity: 1, borderWidth, shadow: false };

  if (state === "selected") {
    item.borderWidth = borderWidth + 2;
    item.shadow = { enabled: true, color: "rgba(0, 0, 0, 0.35)", size: 14, x: 0, y: 2 };
  } else if (state === "related") {
    item.borderWidth = borderWidth + 1;
  } else if (state === "dimmed") {
    item.opacity = DIMMED_ITEM_OPACITY;
    if (base.font) item.font = fadedFont(base.font);
  }
  return item;
}

export function applyEdgeState(base, state) {
  const width = base.width ?? VIS_DEFAULT_EDGE_WIDTH;
  // null (not undefined) resets a key vis-network was given earlier to its default.
  const item = { ...base, width, color: base.color ?? null };

  if (state === "selected") {
    item.width = width + 2;
  } else if (state === "related") {
    item.width = width + 1;
  } else if (state === "dimmed") {
    item.color = { color: base.color, opacity: DIMMED_ITEM_OPACITY, inherit: false };
    if (base.font) item.font = fadedFont(base.font);
  }
  return item;
}

export function translateViewerConfig(config) {
  const cfg = config || {};
  const layout = cfg.layout || {};
  const hierarchical = layout.hierarchical || {};
  const physics = cfg.physics || {};
  const stabilisation = physics.stabilisation || {};
  const interaction = cfg.interaction || {};

  const options = {
    layout: {
      hierarchical: {
        enabled: layout.mode === "hierarchical",
        direction: hierarchical.direction || "UD",
        sortMethod: hierarchical.sort_method || "hubsize",
      },
    },
    physics: {
      enabled: physics.enabled !== false,
      stabilization: {
        enabled: stabilisation.enabled !== false,
        fit: stabilisation.fit !== false,
      },
    },
    interaction: {
      hover: interaction.hover === true,
      zoomView: interaction.zoom_enabled !== false,
      dragView: interaction.drag_view_enabled !== false,
      dragNodes: interaction.drag_nodes_enabled !== false,
      multiselect: interaction.multi_select === true,
    },
  };

  if (hierarchical.level_separation != null) {
    options.layout.hierarchical.levelSeparation = hierarchical.level_separation;
  }
  if (hierarchical.node_spacing != null) {
    options.layout.hierarchical.nodeSpacing = hierarchical.node_spacing;
  }
  if (hierarchical.tree_spacing != null) {
    options.layout.hierarchical.treeSpacing = hierarchical.tree_spacing;
  }

  if (physics.solver != null) {
    options.physics.solver = physics.solver;
  }
  if (stabilisation.iterations != null) {
    options.physics.stabilization.iterations = stabilisation.iterations;
  }

  return options;
}
