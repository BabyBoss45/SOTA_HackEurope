uniform float uTime;
uniform float uAnimation;
uniform vec3 uColor1;
uniform vec3 uColor2;
uniform float uInputVolume;
uniform float uOutputVolume;

varying vec2 vUv;
varying vec3 vNormal;

void main() {
    float activeVolume = max(uInputVolume, uOutputVolume);

    // Dynamic gradient based on normals and time
    float colorMix = dot(vNormal, vec3(sin(uTime), cos(uTime), sin(uTime * 0.5))) * 0.5 + 0.5;
    
    vec3 color = mix(uColor1, uColor2, colorMix);

    // Fresnel glow effect on the edges
    float f = 1.0 - max(dot(viewMatrix[2].xyz, vNormal), 0.0);
    f = pow(f, 2.0); // fresnel intensity
    
    // Core brightness swells with audio
    float glow = 1.2 + activeVolume * 1.5;
    color *= (glow + f);

    // Add some soft transparency on the edges for a gooey look
    float alpha = 0.95 + (f * 0.5);

    gl_FragColor = vec4(color, alpha);
}
