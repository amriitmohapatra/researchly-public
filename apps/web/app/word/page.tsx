import { Taskpane } from "@/components/word/Taskpane";

/**
 * The taskpane Word shows in its sidebar (manifest SourceLocation). Static
 * chrome only here: the document is read in the browser by <Taskpane/> and
 * sent straight to the chosen engine, never to this server.
 */
export default function WordPage() {
  return <Taskpane />;
}
