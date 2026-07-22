{
  "//": "Strict TS base — matches code-style.md ('strict mode always'). init-claude drops this as tsconfig.json (or extend it). Strict catches a class of bugs before runtime.",
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    "noFallthroughCasesInSwitch": true,
    "forceConsistentCasingInFileNames": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler"
  },
  "exclude": ["node_modules", "dist", "build", "coverage"]
}
