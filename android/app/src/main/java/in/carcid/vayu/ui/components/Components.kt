package `in`.carcid.vayu.ui.components

import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.Notifications
import androidx.compose.material.icons.outlined.WifiOff
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import `in`.carcid.vayu.ui.theme.Vayu

// The approved prototype's building blocks. Touch targets are at least 44 dp everywhere.

/** Big bold page title with the bell (count badge) and the profile avatar on the right. */
@Composable
fun VayuTopBar(title: String, initials: String, bellCount: Int, onBell: () -> Unit, onProfile: () -> Unit,
               actions: @Composable RowScope.() -> Unit = {}) {
    Row(Modifier.fillMaxWidth().background(Vayu.colors.bg).padding(start = 20.dp, end = 8.dp, top = 16.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Text(title, style = MaterialTheme.typography.headlineMedium, color = Vayu.colors.ink,
            modifier = Modifier.weight(1f))
        actions()
        IconButton(onClick = onBell, modifier = Modifier.semantics {
            contentDescription = if (bellCount > 0) "Notifications, $bellCount" else "Notifications"
        }) {
            Box {
                Icon(Icons.Outlined.Notifications, contentDescription = null, tint = Vayu.colors.ink)
                if (bellCount > 0) CountBadge(bellCount, Modifier.align(Alignment.TopEnd).offset(6.dp, (-6).dp))
            }
        }
        IconButton(onClick = onProfile, modifier = Modifier.semantics { contentDescription = "Profile" }) {
            Avatar(initials)
        }
    }
}

@Composable
fun CountBadge(count: Int, modifier: Modifier = Modifier) {
    Box(modifier.heightIn(min = 17.dp).clip(RoundedCornerShape(9.dp)).background(Vayu.colors.bad)
        .padding(horizontal = 4.dp), contentAlignment = Alignment.Center) {
        Text(if (count > 99) "99+" else count.toString(), color = Color.White, fontSize = 10.sp,
            fontWeight = FontWeight.Bold)
    }
}

@Composable
fun Avatar(initials: String, size: Int = 32, tint: Color = Vayu.colors.brandTint, ink: Color = Vayu.colors.brand) {
    Box(Modifier.size(size.dp).clip(CircleShape).background(tint), contentAlignment = Alignment.Center) {
        Text(initials, color = ink, fontSize = (size * 0.38).sp, fontWeight = FontWeight.Bold)
    }
}

/** Small uppercase label above a group of rows, e.g. "UNASSIGNED · 3". */
@Composable
fun SectionLabel(text: String, modifier: Modifier = Modifier, trailing: String? = null) {
    Row(modifier.fillMaxWidth().padding(top = 24.dp, bottom = 4.dp)) {
        Text(text.uppercase(), style = MaterialTheme.typography.labelSmall, color = Vayu.colors.muted,
            modifier = Modifier.weight(1f))
        if (trailing != null) Text(trailing, style = MaterialTheme.typography.bodyMedium, color = Vayu.colors.muted)
    }
}

/** One list row with a thin divider: optional leading slot, title and subtitle, trailing slot. */
@Composable
fun ListRow(title: String, modifier: Modifier = Modifier, subtitle: String? = null,
            leading: (@Composable () -> Unit)? = null, trailing: (@Composable () -> Unit)? = null,
            onClick: (() -> Unit)? = null) {
    Column(modifier.fillMaxWidth().let { if (onClick != null) it.clickable(onClick = onClick) else it }) {
        Row(Modifier.fillMaxWidth().heightIn(min = 60.dp).padding(vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            leading?.invoke()
            Column(Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.SemiBold,
                    color = Vayu.colors.ink)
                if (subtitle != null) Text(subtitle, style = MaterialTheme.typography.bodyMedium, color = Vayu.colors.muted)
            }
            trailing?.invoke()
        }
        HorizontalDivider(color = Vayu.colors.line)
    }
}

enum class Tone { NEUTRAL, OK, WARN, BAD, INFO }

@Composable
fun toneColor(t: Tone): Color = when (t) {
    Tone.NEUTRAL -> Vayu.colors.line2
    Tone.OK -> Vayu.colors.ok
    Tone.WARN -> Vayu.colors.warn
    Tone.BAD -> Vayu.colors.bad
    Tone.INFO -> Vayu.colors.info
}

/** A coloured dot and a short status word, e.g. "● In progress". */
@Composable
fun StatusDot(label: String, tone: Tone) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Box(Modifier.size(8.dp).clip(CircleShape).background(toneColor(tone)))
        Text(label, style = MaterialTheme.typography.bodyMedium, color = Vayu.colors.muted, maxLines = 1, softWrap = false)
    }
}

/** Soft segmented switch (Today / Upcoming / All). */
@Composable
fun Segmented(options: List<String>, selected: Int, onSelect: (Int) -> Unit, modifier: Modifier = Modifier) {
    Row(modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Vayu.colors.soft).padding(4.dp),
        horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        options.forEachIndexed { i, label ->
            val on = i == selected
            Box(Modifier.weight(1f).heightIn(min = 36.dp).clip(RoundedCornerShape(9.dp))
                .background(if (on) Vayu.colors.bg else Color.Transparent)
                .selectable(selected = on, role = Role.Tab, onClick = { onSelect(i) }),
                contentAlignment = Alignment.Center) {
                // a tab never breaks mid-word: one line, "…" if it can't fit
                Text(label, style = MaterialTheme.typography.bodyLarge, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                    fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal,
                    color = if (on) Vayu.colors.ink else Vayu.colors.muted, modifier = Modifier.padding(horizontal = 4.dp))
            }
        }
    }
}

/** Up to 4 short answers in one row, one tap each. Defect options turn amber when chosen. */
@Composable
fun ChoiceRow(options: List<Pair<String, Boolean>>, selected: String?, onSelect: (String) -> Unit) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        options.forEach { (label, defect) ->
            val on = label == selected
            val bg = when { on && defect -> Vayu.colors.warn; on -> Vayu.colors.primary; else -> Vayu.colors.soft }
            Box(Modifier.weight(1f).heightIn(min = 48.dp).clip(RoundedCornerShape(12.dp)).background(bg)
                .selectable(selected = on, role = Role.RadioButton, onClick = { onSelect(label) }),
                contentAlignment = Alignment.Center) {
                Text(label, style = MaterialTheme.typography.labelLarge, fontSize = 14.sp,
                    color = when { on && defect -> Vayu.colors.onWarn; on -> Vayu.colors.onPrimary; else -> Vayu.colors.ink2 })
            }
        }
    }
}

/** 5–8 answers or long labels: stacked full-width rows; defects carry a severity tag. */
@Composable
fun StackedOption(label: String, selected: Boolean, severity: String?, onClick: () -> Unit) {
    Row(Modifier.fillMaxWidth().heightIn(min = 52.dp).clip(RoundedCornerShape(12.dp))
        .background(if (selected) Vayu.colors.primary else Vayu.colors.soft)
        .selectable(selected = selected, role = Role.RadioButton, onClick = onClick)
        .padding(horizontal = 14.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(Modifier.size(20.dp).clip(CircleShape).border(
            BorderStroke(if (selected) 6.dp else 2.dp, if (selected) Vayu.colors.onPrimary else Vayu.colors.line2), CircleShape))
        Text(label, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f),
            color = if (selected) Vayu.colors.onPrimary else Vayu.colors.ink)
        if (severity != null) {
            val (bg, fg) = if (severity == "Critical") Vayu.colors.badTint to Vayu.colors.bad else Vayu.colors.warnTint to Vayu.colors.warn
            Text(severity, fontSize = 11.sp, fontWeight = FontWeight.Bold, color = fg,
                modifier = Modifier.clip(RoundedCornerShape(50)).background(bg).padding(horizontal = 7.dp, vertical = 2.dp))
        }
    }
}

/** Tap-on, tap-off chip for multi-select (up to 8 options). */
@Composable
fun ToggleChip(label: String, on: Boolean, onToggle: (Boolean) -> Unit) {
    Box(Modifier.heightIn(min = 42.dp).clip(RoundedCornerShape(21.dp))
        .background(if (on) Vayu.colors.primary else Vayu.colors.soft)
        .toggleable(value = on, role = Role.Checkbox, onValueChange = onToggle)
        .padding(horizontal = 14.dp), contentAlignment = Alignment.Center) {
        Text(label, style = MaterialTheme.typography.bodyLarge, fontSize = 14.sp,
            color = if (on) Vayu.colors.onPrimary else Vayu.colors.ink2)
    }
}

/** Info / warning / problem message; closable when [onClose] is given (the offline strip never is). */
@Composable
fun Banner(text: String, tone: Tone, onClose: (() -> Unit)?, modifier: Modifier = Modifier) {
    val (bg, fg) = when (tone) {
        Tone.WARN -> Vayu.colors.warnTint to Vayu.colors.warn
        Tone.BAD -> Vayu.colors.badTint to Vayu.colors.bad
        Tone.OK -> Vayu.colors.okTint to Vayu.colors.ok
        else -> Vayu.colors.infoTint to Vayu.colors.info
    }
    Row(modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(bg)
        .padding(start = 14.dp, top = 4.dp, bottom = 4.dp, end = if (onClose == null) 14.dp else 0.dp).heightIn(min = 40.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Text(text, style = MaterialTheme.typography.bodyLarge, fontSize = 14.sp, color = fg, modifier = Modifier.weight(1f))
        if (onClose != null) IconButton(onClick = onClose) { Icon(Icons.Outlined.Close, contentDescription = "Close", tint = fg) }
    }
}

/** Always-visible strip while offline. Not closable: it goes away when signal returns. */
@Composable
fun OfflineStrip(text: String, modifier: Modifier = Modifier) {
    Row(modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Vayu.colors.ink)
        .padding(horizontal = 14.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Icon(Icons.Outlined.WifiOff, contentDescription = null, tint = Vayu.colors.bg, modifier = Modifier.size(20.dp))
        Text(text, style = MaterialTheme.typography.bodyLarge, fontSize = 14.sp, color = Vayu.colors.bg)
    }
}

@Composable
fun PrimaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true) {
    Box(modifier.fillMaxWidth().heightIn(min = 54.dp).clip(RoundedCornerShape(14.dp))
        .background(if (enabled) Vayu.colors.primary else Vayu.colors.soft)
        .clickable(enabled = enabled, role = Role.Button, onClick = onClick), contentAlignment = Alignment.Center) {
        Text(text, style = MaterialTheme.typography.labelLarge, fontSize = 16.sp,
            color = if (enabled) Vayu.colors.onPrimary else Vayu.colors.muted)
    }
}

@Composable
fun SoftButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, color: Color = Vayu.colors.ink) {
    // the same height, corners and text size as PrimaryButton: side by side they read as one pair
    Box(modifier.heightIn(min = 54.dp).clip(RoundedCornerShape(14.dp)).background(Vayu.colors.soft)
        .clickable(role = Role.Button, onClick = onClick).padding(horizontal = 16.dp), contentAlignment = Alignment.Center) {
        Text(text, style = MaterialTheme.typography.labelLarge, fontSize = 16.sp, color = color)
    }
}

/** Rounded soft-grey text field with an optional leading icon (sign-in, search, answers). */
@Composable
fun SoftField(value: String, onValueChange: (String) -> Unit, placeholder: String, modifier: Modifier = Modifier,
              icon: ImageVector? = null, trailing: (@Composable () -> Unit)? = null,
              visualTransformation: androidx.compose.ui.text.input.VisualTransformation =
                  androidx.compose.ui.text.input.VisualTransformation.None,
              error: Boolean = false, password: Boolean = false, enabled: Boolean = true,
              /** The keyboard's action key (Next, Done…) and what it does; Next moves to the following field. */
              imeAction: androidx.compose.ui.text.input.ImeAction = androidx.compose.ui.text.input.ImeAction.Default,
              onIme: (() -> Unit)? = null) {
    Row(modifier.fillMaxWidth().heightIn(min = 54.dp).clip(RoundedCornerShape(14.dp)).background(Vayu.colors.soft)
        .let { if (error) it.border(2.dp, Vayu.colors.bad, RoundedCornerShape(14.dp)) else it }
        .padding(start = 16.dp, end = 4.dp), verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        if (icon != null) Icon(icon, contentDescription = null, tint = Vayu.colors.muted, modifier = Modifier.size(20.dp))
        Box(Modifier.weight(1f)) {
            if (value.isEmpty()) Text(placeholder, style = MaterialTheme.typography.bodyLarge, color = Vayu.colors.muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
            BasicTextField(value, onValueChange, enabled = enabled, singleLine = true, visualTransformation = visualTransformation,
                // passwords: no suggestions, no keyboard learning
                keyboardOptions = if (password) androidx.compose.foundation.text.KeyboardOptions(
                    keyboardType = androidx.compose.ui.text.input.KeyboardType.Password, autoCorrectEnabled = false, imeAction = imeAction)
                else androidx.compose.foundation.text.KeyboardOptions(imeAction = imeAction),
                keyboardActions = if (onIme == null) androidx.compose.foundation.text.KeyboardActions.Default
                    else androidx.compose.foundation.text.KeyboardActions(onAny = { onIme() }),
                textStyle = MaterialTheme.typography.bodyLarge.copy(color = if (enabled) Vayu.colors.ink else Vayu.colors.muted),
                cursorBrush = SolidColor(Vayu.colors.ink),
                modifier = Modifier.fillMaxWidth().semantics { contentDescription = placeholder })
        }
        trailing?.invoke() ?: Spacer(Modifier.width(12.dp))
    }
}

/** Shared bottom bar shell; each item is icon over label, the active one in brand red. */
@Composable
fun BottomBar(items: List<Triple<String, ImageVector, Int?>>, active: Int, spinning: Int = -1, onSelect: (Int) -> Unit) {
    Column {
        HorizontalDivider(color = Vayu.colors.line)
        Row(Modifier.fillMaxWidth().background(Vayu.colors.bg).padding(top = 6.dp, bottom = 14.dp)) {
            items.forEachIndexed { i, (label, icon, badge) ->
                val on = i == active
                Column(Modifier.weight(1f).heightIn(min = 52.dp)
                    .selectable(selected = on, role = Role.Tab, onClick = { onSelect(i) })
                    // one steady name for screen readers and tests, even while it says "Updating…"
                    .semantics(mergeDescendants = true) { contentDescription = if (i == spinning) "$label, updating" else label },
                    horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                    Box {
                        Icon(icon, contentDescription = null, tint = if (on || i == spinning) Vayu.colors.brand else Vayu.colors.muted)
                        if (badge != null && badge > 0) Box(Modifier.align(Alignment.TopEnd).offset(10.dp, (-6).dp)
                            .clip(RoundedCornerShape(9.dp)).background(Vayu.colors.info).padding(horizontal = 5.dp)) {
                            Text(badge.toString(), color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                        }
                    }
                    Spacer(Modifier.height(3.dp))
                    // while it works the button says so (no endless animation: lighter, and nothing to wait on)
                    Text(if (i == spinning) "Updating…" else label, fontSize = 12.sp, textAlign = TextAlign.Center, maxLines = 1, overflow = TextOverflow.Ellipsis,
                        fontWeight = if (on || i == spinning) FontWeight.SemiBold else FontWeight.Medium,
                        color = if (on || i == spinning) Vayu.colors.brand else Vayu.colors.muted)
                }
            }
        }
    }
}

/** Horizontal wrap of chips without a layout library (chips scroll sideways if they overflow). */
@Composable
fun ChipRow(content: @Composable RowScope.() -> Unit) {
    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp), content = content)
}

@Composable
fun Page(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Column(modifier.background(Vayu.colors.bg).padding(horizontal = 20.dp), content = content)
}

/**
 * Every bottom sheet: scrolls when it's taller than the screen, and stays above the phone's
 * buttons and the keyboard (its own buttons are never hidden).
 */
@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
fun VayuSheet(onDismiss: () -> Unit, footer: (@Composable () -> Unit)? = null, content: @Composable ColumnScope.() -> Unit) =
    // opens all the way at once (no half-open step to drag up); [footer] stays pinned under the scroll
    androidx.compose.material3.ModalBottomSheet(onDismissRequest = onDismiss, containerColor = Vayu.colors.bg,
        sheetState = androidx.compose.material3.rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(Modifier.navigationBarsPadding().imePadding()) {
            Column(Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState()), content = content)
            footer?.invoke()
        }
    }

/** Pick a day in the app's own colours; days before [notBefore] can't be picked. */
@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
fun DatePick(initial: java.time.LocalDate?, notBefore: java.time.LocalDate?, onPick: (java.time.LocalDate) -> Unit, onDismiss: () -> Unit) {
    val utc = java.time.ZoneOffset.UTC
    fun day(ms: Long) = java.time.Instant.ofEpochMilli(ms).atZone(utc).toLocalDate()
    val state = androidx.compose.material3.rememberDatePickerState(
        initialSelectedDateMillis = initial?.atStartOfDay(utc)?.toInstant()?.toEpochMilli(),
        selectableDates = object : androidx.compose.material3.SelectableDates {
            override fun isSelectableDate(utcTimeMillis: Long) = notBefore == null || !day(utcTimeMillis).isBefore(notBefore)
            override fun isSelectableYear(year: Int) = notBefore == null || year >= notBefore.year
        })
    val colors = androidx.compose.material3.DatePickerDefaults.colors(containerColor = Vayu.colors.bg)
    androidx.compose.material3.DatePickerDialog(onDismissRequest = onDismiss, colors = colors,
        confirmButton = { androidx.compose.material3.TextButton({ state.selectedDateMillis?.let { onPick(day(it)) } }, enabled = state.selectedDateMillis != null) { Text("OK") } },
        dismissButton = { androidx.compose.material3.TextButton(onDismiss) { Text("Cancel") } }) {
        androidx.compose.material3.DatePicker(state, colors = colors, showModeToggle = false)
    }
}

/** Pick a time (12-hour clock) in the app's own colours. */
@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
fun TimePick(initial: java.time.LocalTime, onPick: (java.time.LocalTime) -> Unit, onDismiss: () -> Unit) {
    val state = androidx.compose.material3.rememberTimePickerState(initial.hour, initial.minute, is24Hour = false)
    androidx.compose.material3.AlertDialog(onDismissRequest = onDismiss, containerColor = Vayu.colors.bg,
        confirmButton = { androidx.compose.material3.TextButton({ onPick(java.time.LocalTime.of(state.hour, state.minute)) }) { Text("OK") } },
        dismissButton = { androidx.compose.material3.TextButton(onDismiss) { Text("Cancel") } },
        text = { androidx.compose.material3.TimePicker(state) })
}
