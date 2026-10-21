@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title bruxosdovfx - Easy Install (MiniMax H3 + SyncTile)

rem ============================================================================
rem  bruxosdovfx - instalador de custom nodes, modelos e LoRAs (MiniMax H3)
rem  Coloque este .bat na pasta do ComfyUI (ou na pasta do ComfyUI-Easy-Install)
rem  e de dois cliques. O que ja estiver instalado (mesmo nome) e ignorado.
rem ============================================================================

rem ---------------- OPCOES (edite se quiser) ----------------
rem Text encoder: int8 (27 GB, padrao do workflow) ou nvfp4 (15,7 GB, menos RAM)
set "TEXT_ENCODER=int8"
rem VAE de video: light (Kijai, rapido, padrao do workflow) ou full (Comfy-Org int8, mais detalhe)
set "VAE_VIDEO=light"
rem 1 = baixa tambem os LoRAs opcionais (PDMD 4 passos e LMS); 0 = so o Background Replace v3
set "LORAS_OPCIONAIS=1"
rem 1 = atualiza (git pull) os custom nodes que ja estao instalados via git; 0 = so ignora
set "ATUALIZAR_NODES=0"
rem -----------------------------------------------------------

echo.
echo  ==============================================================
echo    bruxosdovfx  -  Easy Install  MiniMax H3 + SyncTile
echo  ==============================================================
echo.

set /a N_OK=0, N_SKIP=0, N_FAIL=0

rem ---------- 1. achar a pasta do ComfyUI ----------
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"
set "COMFY="
call :is_comfy "%HERE%"
if not defined COMFY call :is_comfy "%HERE%\ComfyUI"
if not defined COMFY call :is_comfy "%HERE%\ComfyUI-Easy-Install\ComfyUI"
if not defined COMFY call :is_comfy "%HERE%\.."
if not defined COMFY call :is_comfy "%HERE%\..\.."
if not defined COMFY for /d %%D in ("%HERE%\*") do if not defined COMFY call :is_comfy "%%~fD\ComfyUI"
if not defined COMFY (
  echo  [ERRO] Nao encontrei o ComfyUI ^(pasta com main.py e custom_nodes^).
  echo         Coloque este arquivo dentro da pasta ComfyUI e rode de novo.
  goto :fim
)
set "CN=%COMFY%\custom_nodes"
set "MODELS=%COMFY%\models"
echo  ComfyUI .......... %COMFY%

rem ---------- 2. ferramentas: python, git, curl ----------
set "PY="
for %%P in ("%COMFY%\..\python_embeded\python.exe" "%COMFY%\..\..\python_embeded\python.exe" "%COMFY%\python_embeded\python.exe" "%COMFY%\venv\Scripts\python.exe" "%COMFY%\.venv\Scripts\python.exe" "%COMFY%\..\venv\Scripts\python.exe" "%COMFY%\..\.venv\Scripts\python.exe") do (
  if not defined PY if exist "%%~fP" set "PY=%%~fP"
)
if not defined PY for /f "delims=" %%P in ('where python 2^>nul') do if not defined PY set "PY=%%P"
if defined PY (echo  Python ........... !PY!) else (echo  [AVISO] Python do ComfyUI nao encontrado: as dependencias dos nodes nao serao instaladas.)

set "GIT="
for /f "delims=" %%G in ('where git 2^>nul') do if not defined GIT set "GIT=%%G"
for %%G in ("%COMFY%\..\git\cmd\git.exe" "%COMFY%\..\..\git\cmd\git.exe" "%COMFY%\..\PortableGit\cmd\git.exe" "%COMFY%\..\..\PortableGit\cmd\git.exe") do (
  if not defined GIT if exist "%%~fG" set "GIT=%%~fG"
)
if defined GIT (echo  Git .............. !GIT!) else (echo  Git .............. nao encontrado ^(vou baixar os nodes em .zip^))

where curl >nul 2>&1
if errorlevel 1 (
  echo  [ERRO] curl nao encontrado. Ele vem com o Windows 10/11; atualize o Windows ou instale o curl.
  goto :fim
)
echo.

rem ---------- 3. custom nodes ----------
echo  ------------------------- CUSTOM NODES -------------------------
if exist "%CN%\ComfyUI-SyncTile-H3\" (
  set "DIS=ComfyUI-SyncTile-H3.disabled"
  if exist "%CN%\!DIS!" set "DIS=ComfyUI-SyncTile-H3.disabled_%RANDOM%"
  ren "%CN%\ComfyUI-SyncTile-H3" "!DIS!"
  echo  [ok]  versao antiga ComfyUI-SyncTile-H3 desativada ^(renomeada para !DIS!^)
)
rem  :node  tipo-de-marca  marca  dono/repo  pasta  nome
call :node F synctile_nodes.py "NyckM/Bruxosdovfx-SyncTile-MiniMax-H3-v5.4" "bruxosdovfx-SyncTile" "bruxosdovfx SyncTile"
call :node F bruxos_save_video_v2.py "NyckM/Video-Util-ComfYUI" "Video-Util-ComfYUI" "bruxosdovfx Media IO - Load/Save Video Pro"
call :node T MinimaxH3LatentUpscaler3D "LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler" "Comfyui_Minimax_h3_latent_Upscaler" "MiniMax H3 Latent Upscaler - LBH"
call :node T "easy loraStack" "yolain/ComfyUI-Easy-Use" "ComfyUI-Easy-Use" "ComfyUI-Easy-Use - loraStack"
echo.

rem ---------- 4. modelos ----------
echo  ---------------------------- MODELOS ----------------------------
set "HF=https://huggingface.co"

set "U_UNET=%HF%/MATLOWAI/minimax-h3-fused-turbo-int8-convrot/resolve/main/diffusion_models/minimax_h3_fused_refdelta_r1024_turbo8_mystic07_int8_convrot.safetensors"
call :model diffusion_models Minimax "minimax_h3_fused_refdelta_r1024_turbo8_mystic07_int8_convrot.safetensors" U_UNET unet "21 GB"

if /i "%TEXT_ENCODER%"=="nvfp4" (
  set "U_TE=%HF%/Comfy-Org/MiniMax-H3/resolve/main/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
  call :model text_encoders "" "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors" U_TE clip "15,7 GB"
) else (
  set "U_TE=%HF%/Comfy-Org/MiniMax-H3/resolve/main/text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors"
  call :model text_encoders "" "qwen3vl_32b_minimax_h3_int8_convrot.safetensors" U_TE clip "27 GB"
)

if /i "%VAE_VIDEO%"=="full" (
  set "U_VAE=%HF%/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_video_vae_int8_convrot.safetensors"
  call :model vae Minimax "minimax_h3_video_vae_int8_convrot.safetensors" U_VAE "" "2,8 GB"
) else (
  set "U_VAE=%HF%/Kijai/MiniMax-H3-experimental/resolve/main/minimax_h3_lynnreal_light_vae_int8_convrot.safetensors"
  call :model vae Minimax "minimax_h3_lynnreal_light_vae_int8_convrot.safetensors" U_VAE "" "VAE leve"
)

set "U_AVAE=%HF%/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_audio_vae_fp32.safetensors"
call :model vae Minimax "minimax_h3_audio_vae_fp32.safetensors" U_AVAE "" "VAE de audio"

set "U_UPS=%HF%/LBH-123-AI/Minimax_h3_latent_Upscaler/resolve/main/minimax_h3_latent_upscaler_3d_conv_v1/minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors"
call :model latent_upscale_models "" "minimax_h3_latent_upscaler_3d_conv_v1_bf16.safetensors" U_UPS "" "691 MB"
echo.

rem ---------- 5. LoRAs ----------
echo  ----------------------------- LORAS -----------------------------
set "U_BR=%HF%/NyckM/Background_Replace_Minimax_H3/resolve/main/Background%%20Replace%%20v3.safetensors"
call :model loras minimax "Background Replace v3.safetensors" U_BR "" "1,9 GB"
if "%LORAS_OPCIONAIS%"=="1" (
  set "U_PDMD=%HF%/Kijai/MiniMax-H3-experimental/resolve/main/loras/minimax_h3_pdmd_4step_lora_avg_rank_57_bf16.safetensors"
  call :model loras minimax "minimax_h3_pdmd_4step_lora_avg_rank_57_bf16.safetensors" U_PDMD "" "opcional"
  set "U_LMS=%HF%/Alissonerdx/Minimax-H3-ComfyUI/resolve/main/loras/minimax_h3_lms_v1.0_r64.safetensors"
  call :model loras minimax "minimax_h3_lms_v1.0_r64.safetensors" U_LMS "" "opcional"
)

echo.
echo  ==============================================================
echo    Pronto. Instalados: !N_OK!   Ja existiam: !N_SKIP!   Falhas: !N_FAIL!
echo    Reinicie o ComfyUI. O console deve mostrar:
echo    [bruxosdovfx • SyncTile] v5.x carregado
echo  ==============================================================
if not "!N_FAIL!"=="0" echo    Algo falhou: rode de novo ^(os downloads continuam de onde pararam^).
goto :fim


rem ======================= SUB-ROTINAS =======================
:is_comfy
if exist "%~1\main.py" if exist "%~1\custom_nodes\" set "COMFY=%~f1"
exit /b 0

rem :node  F^|T  marca  dono/repo  pasta  nome
rem   F = existe algum custom_nodes\*\marca     T = algum .py contem o texto marca
:node
set "FOUNDDIR="
if /i "%~1"=="F" (
  for /d %%D in ("%CN%\*") do (
    if not defined FOUNDDIR if exist "%%~fD\%~2" (
      echo %%~nxD | findstr /i /c:".disabled" >nul || set "FOUNDDIR=%%~fD"
    )
  )
) else (
  for /f "delims=" %%F in ('findstr /s /m /l /c:"%~2" "%CN%\*.py" 2^>nul') do (
    if not defined FOUNDDIR (
      echo %%F | findstr /i /c:".disabled" >nul || set "FOUNDDIR=%%~dpF"
    )
  )
)
if defined FOUNDDIR (
  if "%ATUALIZAR_NODES%"=="1" if defined GIT (
    "!GIT!" -C "!FOUNDDIR!" rev-parse --is-inside-work-tree >nul 2>&1 && (
      echo  [..]  %~5: atualizando ^(git pull^)
      "!GIT!" -C "!FOUNDDIR!" pull --ff-only
      exit /b 0
    )
  )
  echo  [--]  %~5: ja instalado, ignorado
  set /a N_SKIP+=1
  exit /b 0
)
set "DEST=%CN%\%~4"
if exist "!DEST!\" (
  echo  [--]  %~5: pasta %~4 ja existe, ignorado
  set /a N_SKIP+=1
  exit /b 0
)
echo  [..]  %~5: instalando em !DEST!
if defined GIT (
  "!GIT!" clone --depth 1 "https://github.com/%~3.git" "!DEST!"
  if errorlevel 1 goto :node_zip
) else (
  goto :node_zip
)
goto :node_reqs
:node_zip
set "ZTMP=%CN%\_bruxos_tmp_%RANDOM%"
mkdir "!ZTMP!" >nul 2>&1
curl -L --fail --retry 3 -o "!ZTMP!\repo.zip" "https://github.com/%~3/archive/refs/heads/main.zip"
if errorlevel 1 (
  echo  [ERRO] %~5: download falhou
  set /a N_FAIL+=1
  rmdir /s /q "!ZTMP!" >nul 2>&1
  exit /b 1
)
tar -xf "!ZTMP!\repo.zip" -C "!ZTMP!"
set "ZDIR="
for /d %%Z in ("!ZTMP!\*") do if not defined ZDIR set "ZDIR=%%~fZ"
move "!ZDIR!" "!DEST!" >nul
rmdir /s /q "!ZTMP!" >nul 2>&1
:node_reqs
if not exist "!DEST!\" (
  echo  [ERRO] %~5: nao instalou
  set /a N_FAIL+=1
  exit /b 1
)
if exist "!DEST!\requirements.txt" if defined PY (
  set "REQ=!DEST!\requirements.txt"
  "!PY!" -c "import cv2" >nul 2>&1
  if not errorlevel 1 (
    findstr /v /i /b /c:"opencv" "!DEST!\requirements.txt" > "%TEMP%\bruxos_req.txt"
    set "REQ=%TEMP%\bruxos_req.txt"
  )
  echo  [..]  %~5: instalando dependencias
  "!PY!" -m pip install -r "!REQ!"
)
echo  [ok]  %~5
set /a N_OK+=1
exit /b 0

rem :model  pasta-tipo  subpasta  arquivo  VAR_URL  pasta-alternativa  tamanho
:model
set "NAME=%~3"
set "URL=!%~4!"
set "FOUND="
if exist "%MODELS%\%~1\" for /f "delims=" %%F in ('dir /s /b "%MODELS%\%~1\%~3" 2^>nul') do if not defined FOUND set "FOUND=%%F"
if not defined FOUND if not "%~5"=="" if exist "%MODELS%\%~5\" for /f "delims=" %%F in ('dir /s /b "%MODELS%\%~5\%~3" 2^>nul') do if not defined FOUND set "FOUND=%%F"
if defined FOUND (
  echo  [--]  !NAME!: ja existe, ignorado
  set /a N_SKIP+=1
  exit /b 0
)
if "%~2"=="" (set "DIR=%MODELS%\%~1") else (set "DIR=%MODELS%\%~1\%~2")
if not exist "!DIR!\" mkdir "!DIR!"
echo  [..]  !NAME!  ^(%~6^)  -^>  !DIR!
curl -L --fail --retry 5 --retry-delay 5 -C - -o "!DIR!\!NAME!.part" "!URL!"
if errorlevel 1 (
  echo  [ERRO] !NAME!: download falhou ^(rode de novo para continuar^)
  set /a N_FAIL+=1
  exit /b 1
)
move /y "!DIR!\!NAME!.part" "!DIR!\!NAME!" >nul
echo  [ok]  !NAME!
set /a N_OK+=1
exit /b 0

:fim
echo.
pause
endlocal
