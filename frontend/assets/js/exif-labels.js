// Admin 라이트박스(lightbox.js)와 공유 슬라이드쇼(pages/slideshow.js)의 정보 패널
// EXIF 라벨을 하나로 통일하기 위한 공용 딕셔너리. 두 곳 모두 이 객체를 통해서만
// 라벨 문자열을 만들어야 한/영 혼용이 다시 벌어지지 않는다.
export const EXIF_LABELS = {
  filename: '파일명',
  date: '촬영일시',
  resolution: '해상도',
  make: '제조사',
  camera: '카메라',
  software: '소프트웨어',
  shootMode: '촬영 모드',
  exposure: '노출 시간',
  aperture: '조리개',
  iso: 'ISO',
  focalLength: '초점거리',
  flash: '플래시',
  metering: '측광',
  exposureMode: '노출 모드',
};
