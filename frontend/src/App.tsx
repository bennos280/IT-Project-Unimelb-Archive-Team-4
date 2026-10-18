import { Button } from "@/components/ui/button";
import ImportScreen from "./import/ImportScreen";
import ReviewScreen from "./review-screen/ReviewScreen";
import { useReviewSession } from "./review-screen/useReviewSession";
import ProgressDashboard from "./progress/ProgressDashboard";
import SettingsScreen from "./settings/SettingsScreen";

// Mount the review session only on survey URLs, avoiding API calls on the dashboard.
function SurveyReview() {
  const session = useReviewSession();
  return <><Button asChild variant="link" className="m-2"><a href="/">← Back to all bundles</a></Button><ReviewScreen session={session}/></>;
}
export default function App() {
  const view = new URLSearchParams(location.search).get("view");
  if (view === "import") return <ImportScreen/>;
  if (view === "settings") return <SettingsScreen/>;
  return new URLSearchParams(location.search).has("survey") ? <SurveyReview/> : <ProgressDashboard/>;
}
