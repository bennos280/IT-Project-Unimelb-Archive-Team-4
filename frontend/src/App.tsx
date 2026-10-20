import CollectionsScreen from "./collections/CollectionsScreen";
import ImportScreen from "./import/ImportScreen";
import ReviewScreen from "./review-screen/ReviewScreen";
import { useReviewSession } from "./review-screen/useReviewSession";
import ProgressDashboard from "./progress/ProgressDashboard";
import SettingsScreen from "./settings/SettingsScreen";
import { itemParam, seriesParam } from "./progress/backend";

// Mount the review session only on survey URLs, avoiding API calls on the dashboard.
function SurveyReview() {
  const session = useReviewSession();
  return <ReviewScreen session={session}/>;
}
// Home lists the series; /?series=<id> is one series' items.
export default function App() {
  const params = new URLSearchParams(location.search);
  const view = params.get("view");
  if (view === "import") return <ImportScreen/>;
  if (view === "settings") return <SettingsScreen/>;
  if (params.has("survey")) return <SurveyReview/>;
  return seriesParam(params) || itemParam(params) ? <ProgressDashboard/> : <CollectionsScreen/>; // an item alone: series 1
}
