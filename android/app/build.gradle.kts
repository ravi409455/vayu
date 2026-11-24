import java.io.File
import java.util.Properties

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
    // Release signing: the key and its passwords live outside the project (backed up offline), in
    // ~/vayu-keys/keystore.properties (or the file VAYU_KEYSTORE_PROPS names):
    //   storeFile=/Users/you/vayu-keys/vayu-release.jks  storePassword=…  keyAlias=vayu  keyPassword=…
    val signingProps = File(System.getenv("VAYU_KEYSTORE_PROPS")
        ?: "${System.getProperty("user.home")}/vayu-keys/keystore.properties")
    val signing: Properties? = signingProps.takeIf { it.isFile }?.let { f ->
        Properties().apply { f.inputStream().use { input -> load(input) } }
    }
    if (signing != null) signingConfigs.create("release") {
        storeFile = file(signing.getProperty("storeFile"))
        storePassword = signing.getProperty("storePassword")
        keyAlias = signing.getProperty("keyAlias")
        keyPassword = signing.getProperty("keyPassword")
    }
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
            if (signing != null) signingConfig = signingConfigs.getByName("release")
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

// A release build made here must be signed with the real key: without it, stop (an unsigned or
// wrongly signed APK could never update phones). CI builds it unsigned only to check it compiles.
tasks.matching { it.name == "assembleRelease" }.configureEach {
    doFirst {
        if (System.getenv("CI") == null && !project.android.signingConfigs.names.contains("release"))
            throw GradleException("Release signing key not found. Put keystore.properties in ~/vayu-keys " +
                "(or set VAYU_KEYSTORE_PROPS). See docs/plan-android.md, release signing.")
    }
}

// Robolectric's Android jars come through Gradle (cached, retried) and the tests run offline. Left to
// itself Robolectric downloads them at test time over plain HTTP, which failed in CI (IOException at
// MavenArtifactFetcher). Add a jar here when a test uses another sdk level.
// One configuration per jar: in a single one Gradle would keep only the newest version of the module.
val robolectricSdks = mapOf(
    "34" to "14-robolectric-10818077-i7",
    "35" to "15-robolectric-12650502-i7",
)
val robolectricJars = robolectricSdks.map { (sdk, version) ->
    configurations.create("robolectricSdk$sdk").also {
        dependencies.add(it.name, "org.robolectric:android-all-instrumented:$version")
    }
}
val robolectricDir = layout.buildDirectory.dir("robolectric-jars")
val copyRobolectricJars by tasks.registering(Copy::class) {
    from(robolectricJars)
    into(robolectricDir)
}
tasks.withType<Test>().configureEach {
    dependsOn(copyRobolectricJars)
    systemProperty("robolectric.offline", "true")
    systemProperty("robolectric.dependency.dir", robolectricDir.get().asFile.absolutePath)
}
