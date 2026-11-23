package `in`.carcid.vayu

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import `in`.carcid.vayu.ui.theme.Vayu
import `in`.carcid.vayu.ui.theme.VayuTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent { VayuTheme { VayuApp() } }
    }
}

@Composable
fun VayuApp() {
    Box(Modifier.fillMaxSize().background(Vayu.colors.bg), contentAlignment = Alignment.Center) {
        Text("Vayu", style = MaterialTheme.typography.headlineMedium, color = Vayu.colors.ink)
    }
}
