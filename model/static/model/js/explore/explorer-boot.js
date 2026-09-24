/**
 * Live Explorer page wiring.
 *
 * The behaviour lives in explorer-controller.js; this file only chooses the
 * live data source (server requests over GET) and the page's own canvas
 * background helper. Nothing here edits the model.
 */

import { applyCanvasBackground } from "../appearance/appearance-form.js";
import { createExplorer } from "./explorer-controller.js";
import { createRemoteSource } from "./remote-source.js";

export function startExplorer({ OnyxJarViewer, bootstrap }) {
  return createExplorer({
    OnyxJarViewer,
    bootstrap,
    source: createRemoteSource({ urls: bootstrap.urls }),
    applyBackground: applyCanvasBackground,
  });
}
