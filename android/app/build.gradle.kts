plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.roborazzi)
    alias(libs.plugins.kover)
    alias(libs.plugins.google.services)
}

roborazzi { outputDir.set(file("src/test/screenshots")) }

// plan NF11: the domain and data code (core/) stays at least 80% covered by tests
kover {
    reports {
        filters { includes { packages("in.carcid.vayu.core") } }
        verify { rule { minBound(80) } }
    }
}

android {
    namespace = "in.carcid.vayu"
    compileSdk = 35

    defaultConfig {
        // one processor type only (smaller APK to copy to a test phone): -Pvayu.abi=arm64-v8a
        (project.findProperty("vayu.abi") as String?)?.let { ndk { abiFilters += it } }
        applicationId = "in.carcid.vayu"
        minSdk = 30          // Android 11
        targetSdk = 35
        // release builds set these: -Pvayu.versionCode=2 -Pvayu.versionName=0.2.0
        versionCode = (project.findProperty("vayu.versionCode") as String?)?.toInt() ?: 1
        versionName = (project.findProperty("vayu.versionName") as String?) ?: "0.1.0"
    }

    // crash reports: the Sentry DSN comes from -Pvayu.sentryDsn or SENTRY_DSN_ANDROID (never in git);
    // empty = no reports
    val sentryDsn = (project.findProperty("vayu.sentryDsn") as String?) ?: System.getenv("SENTRY_DSN_ANDROID") ?: ""
    defaultConfig { buildConfigField("String", "SENTRY_DSN", "\"$sentryDsn\"") }
    buildTypes {
        // the API the app talks to; override with -Pvayu.apiUrl=... (e.g. staging)
        val apiUrl = project.findProperty("vayu.apiUrl") as String?
        debug {
            manifestPlaceholders["cleartext"] = "true"     // the local API is plain http
            // an emulator reaches this Mac at 10.0.2.2
            buildConfigField("String", "API_URL", "\"${apiUrl ?: "http://10.0.2.2:8000/api/v1/"}\"")
        }
        release {
            manifestPlaceholders["cleartext"] = "false"
            buildConfigField("String", "API_URL", "\"${apiUrl ?: "https://app.carcid.in/api/v1/"}\"")
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures { compose = true; buildConfig = true }
    testOptions { unitTests.isIncludeAndroidResources = true }
}

dependencies {
    implementation(platform(libs.firebase.bom))
    implementation(libs.firebase.messaging)
    implementation(libs.sentry.android)
    implementation(libs.androidx.core.ktx)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.okhttp)
    implementation(libs.coroutines.android)
    implementation(libs.lifecycle.viewmodel.compose)
    implementation(libs.lifecycle.runtime.compose)
    implementation(libs.work.runtime)
    implementation(libs.camera.core)
    implementation(libs.camera.camera2)
    implementation(libs.camera.lifecycle)
    implementation(libs.camera.view)
    implementation(libs.camera.video)
    implementation(libs.mlkit.text)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.material3)
    implementation(libs.compose.material.icons)
    implementation(libs.compose.ui.tooling.preview)
    debugImplementation(libs.compose.ui.tooling)
    debugImplementation(libs.compose.ui.test.manifest)

    testImplementation(libs.junit)
    testImplementation(libs.robolectric)
    testImplementation(libs.okhttp.mockwebserver)
    testImplementation(libs.coroutines.test)
    testImplementation(platform(libs.compose.bom))
    testImplementation(libs.compose.ui.test.junit4)
    testImplementation(libs.roborazzi)
    testImplementation(libs.roborazzi.compose)
    testImplementation(libs.roborazzi.junit)
    testImplementation(libs.work.testing)
}
