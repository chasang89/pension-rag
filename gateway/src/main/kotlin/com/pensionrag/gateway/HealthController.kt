package com.pensionrag.gateway

import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.RestController

/**
 * 기동 확인용 헬스 엔드포인트.
 *
 * RAG Core 프록시 라우팅과 JWT 인증은 build.gradle.kts의 TODO 참고.
 */
@RestController
class HealthController {

    @GetMapping("/health")
    fun health(): Map<String, String> = mapOf("status" to "ok")
}
