package `in`.carcid.vayu.ui.components

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.List
import androidx.compose.material.icons.outlined.BarChart
import androidx.compose.material.icons.outlined.CalendarToday
import androidx.compose.material.icons.outlined.CloudUpload
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.Work
import androidx.compose.runtime.Composable

enum class OpsTab { TODAY, BOOKINGS, DASHBOARD }
enum class ExpertTab { JOBS, UPLOADS }

/** Ops: Today · Bookings · Dashboard · Refresh (kept clean, nothing else). */
@Composable
fun OpsBottomBar(active: OpsTab, onTab: (OpsTab) -> Unit, onRefresh: () -> Unit, refreshing: Boolean = false) =
    BottomBar(listOf(Triple("Today", Icons.Outlined.CalendarToday, null),
        Triple("Bookings", Icons.AutoMirrored.Outlined.List, null),
        Triple("Dashboard", Icons.Outlined.BarChart, null),
        Triple("Refresh", Icons.Outlined.Refresh, null)), active.ordinal, spinning = if (refreshing) 3 else -1) {
        if (it == 3) onRefresh() else onTab(OpsTab.entries[it])
    }

/** Expert: Jobs · Uploads (count) · Refresh. */
@Composable
fun ExpertBottomBar(active: ExpertTab, uploads: Int, onTab: (ExpertTab) -> Unit, onRefresh: () -> Unit, refreshing: Boolean = false) =
    BottomBar(listOf(Triple("Jobs", Icons.Outlined.Work, null),
        Triple("Uploads", Icons.Outlined.CloudUpload, uploads),
        Triple("Refresh", Icons.Outlined.Refresh, null)), active.ordinal, spinning = if (refreshing) 2 else -1) {
        if (it == 2) onRefresh() else onTab(ExpertTab.entries[it])
    }
