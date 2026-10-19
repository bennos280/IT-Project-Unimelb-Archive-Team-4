import CollectionsScreen from "./collections/CollectionsScreen";
import ImportScreen from "./import/ImportScreen";
import ReviewScreen from "./review-screen/ReviewScreen";
import { useReviewSession } from "./review-screen/useReviewSession";
import ProgressDashboard from "./progress/ProgressDashboard";
import PageTypesScreen from "./settings/PageTypesScreen";
import SettingsScreen from "./settings/SettingsScreen";
import TasksScreen, { TaskScreen } from "./tasks/TasksScreen";

// Mount the review session only on survey URLs, avoiding API calls on the dashboard.
function SurveyReview() {
  const session = useReviewSession();
  return <ReviewScreen session={session}/>;
}
// Home lists the collections; /?collection=<id> is one collection's bundles.
export default function App() {
  const params = new URLSearchParams(location.search);
  const view = params.get("view");
  if (view === "import") return <ImportScreen/>;
  if (view === "settings") return <SettingsScreen/>;
  if (view === "tasks") return params.get("task") ? <TaskScreen id={params.get("task")!}/> : <TasksScreen/>;
  if (view === "setup" || view === "page-types") return <PageTypesScreen/>; // page-types: the old name of a series' Setup
  if (params.has("survey")) return <SurveyReview/>;
  return params.has("collection") || params.has("bundle") ? <ProgressDashboard/> : <CollectionsScreen/>; // an old /?bundle= link: collection 1
}
